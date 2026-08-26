import json

import pytest
from app.ai.persistence.checkpoints import load_checkpoint, save_checkpoint
from app.ai.runtime.factory import build_agent_runtime
from app.ai.runtime.local import LocalDeterministicAgentRuntime
from app.application.operations import touch_worker_heartbeat
from app.config import Settings
from app.db import build_session_factory, init_database, prepare_worker_database
from app.errors import GroundloomError
from app.ids import new_id
from app.main import create_app
from app.models import DeletionRequest, OutboxMessage
from app.outbox import publish_pending
from app.telemetry import LocalTelemetry, build_telemetry
from fastapi.testclient import TestClient


def test_runtime_is_scoped_and_local_is_explicit():
    runtime = build_agent_runtime("local")
    assert isinstance(runtime, LocalDeterministicAgentRuntime)
    assert runtime.capabilities()["canonical_commit"] is False
    assert runtime.capabilities()["unrestricted_shell"] is False


def test_production_refuses_unsafe_defaults():
    settings = Settings(
        env="production", database_url="sqlite:///unsafe.db", model_provider="local"
    )
    try:
        settings.validate_runtime()
    except RuntimeError as exc:
        assert "PostgreSQL" in str(exc)
    else:
        raise AssertionError("Production accepted an unsafe local configuration")


def test_production_worker_helper_uses_worker_role_without_bootstrap(monkeypatch):
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom_api:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
    )
    observed = {}

    class FakeEngine:
        pass

    engine = FakeEngine()

    def fake_make_engine(url):
        observed["url"] = url
        return engine

    monkeypatch.setattr("app.db.make_engine", fake_make_engine)
    monkeypatch.setattr(
        "app.db.build_session_factory",
        lambda url, bound_engine: (url, bound_engine),
    )
    url, actual_engine, factory = prepare_worker_database(settings)
    assert url == "postgresql+psycopg://groundloom_worker:password@localhost/groundloom"
    assert observed["url"] == url
    assert actual_engine is engine
    assert factory == (url, engine)


def test_non_sqlite_app_startup_does_not_apply_schema_bootstrap(monkeypatch):
    settings = Settings(
        env="staging",
        database_url="postgresql+psycopg://groundloom_api:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
        migration_database_url="postgresql+psycopg://groundloom_migrator:password@localhost/groundloom",
        auth_mode="hmac",
        auth_secret="staging-test-secret-that-is-long-enough",
    )

    class FakeEngine:
        pass

    monkeypatch.setattr("app.main.make_engine", lambda _url: FakeEngine())
    monkeypatch.setattr(
        "app.main.apply_migrations",
        lambda _url: pytest.fail("API startup must not apply migrations"),
    )
    monkeypatch.setattr(
        "app.main.init_database",
        lambda _url: pytest.fail("API startup must not initialize schema"),
    )
    create_app(settings)


def test_openapi_contains_contract_boundary(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'contract.db'}", object_store_path=tmp_path / "objects"
    )
    schema = TestClient(create_app(settings)).get("/openapi.json").json()
    assert "/v1/projects" in schema["paths"]
    assert "/v1/patches/{patch_id}/accept" in schema["paths"]
    assert "/v1/exports/{export_id}/download" in schema["paths"]
    assert "/v1/skills/ai-drafts" in schema["paths"]
    assert "/v1/delegated-tasks/{task_id}/retry" in schema["paths"]
    assert "/v1/projects/{project_id}/deletion" in schema["paths"]
    assert "/v1/deletions/{deletion_id}" in schema["paths"]
    assert "/v1/source-versions/{version_id}/index-rebuilds" in schema["paths"]
    assert "/v1/index-rebuilds/{job_id}" in schema["paths"]
    assert "/v1/workspace/preferences" in schema["paths"]
    assert "/ready" in schema["paths"] and "/live" in schema["paths"]
    json.dumps(schema)


def test_health_readiness_and_liveness_expose_bounded_operational_state(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'health.db'}", object_store_path=tmp_path / "objects"
    )
    api = TestClient(create_app(settings))
    assert api.get("/live").json() == {"status": "ok"}
    ready = api.get("/ready")
    assert ready.status_code == 200
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert body["checkpointer"] == "local"
    assert len(body["config_fingerprint"]) == 16
    assert body["oldest_queue_age_seconds"] is None or body["oldest_queue_age_seconds"] >= 0
    assert body["warnings"] == []


def test_health_survives_a_worker_heartbeat_read_back_from_sqlite(tmp_path):
    """Regression test: SQLite has no native timezone-aware datetime type, so
    a WorkerHeartbeat.last_seen read back fresh from storage comes back
    naive while utcnow() is aware. Subtracting them used to raise
    `TypeError: can't subtract offset-naive and offset-aware datetimes` and
    turned every GET /health and /ready into an unhandled 500 the moment any
    worker had ever run — reproduced live via `python
    backend/scripts/ingestion_worker.py --once` against a persistent db,
    then GET /health."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'heartbeat.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with app.state.session_factory() as db:
        touch_worker_heartbeat(db, "worker-1", "ingestion", status="healthy")
        db.commit()

    # A fresh TestClient request opens a new session, forcing SQLAlchemy to
    # issue a real SELECT and read the heartbeat back from SQLite rather than
    # reusing the in-memory (still-aware) object from the write above.
    api = TestClient(app)
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert body["worker_heartbeat"] in {"ok", "stale"}


def test_health_survives_a_queued_job_created_at_read_back_from_sqlite(tmp_path):
    """Same naive/aware SQLite gap as the heartbeat regression above, hit via
    the oldest_queue_age_seconds calculation instead: any of the six
    queued/pending models' `created_at` can trigger the identical
    `now - <naive db value>` TypeError once read back fresh from storage."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'queue-age.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with app.state.session_factory() as db:
        db.add(
            DeletionRequest(
                id=new_id("del"),
                workspace_id=settings.local_workspace_id,
                scope_type="project",
                resource_id="prj_probe",
                requested_by=settings.local_user_id,
                status="pending",
            )
        )
        db.commit()

    api = TestClient(app)
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert body["oldest_queue_age_seconds"] is not None
    assert body["oldest_queue_age_seconds"] >= 0


def test_health_warns_when_model_provider_and_checkpoint_backend_are_mismatched(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'health-warn.db'}",
        object_store_path=tmp_path / "objects",
        model_provider="openai",
    )
    api = TestClient(create_app(settings))
    body = api.get("/health").json()
    assert len(body["warnings"]) == 1
    assert "checkpoint_backend" in body["warnings"][0]
    assert "AGENT_MISCONFIGURED" in body["warnings"][0]


def test_checkpoint_scope_and_redacted_telemetry(tmp_path):
    settings = Settings(object_store_path=tmp_path / "objects")
    save_checkpoint(settings, "workspace", "project", "thread", {"cursor": 3})
    assert load_checkpoint(settings, "workspace", "project", "thread") == {"cursor": 3}
    with pytest.raises(GroundloomError):
        save_checkpoint(settings, "workspace/other", "project", "thread", {})
    telemetry = build_telemetry("local")
    assert isinstance(telemetry, LocalTelemetry)
    telemetry.emit(
        "test",
        {
            "content": "private",
            "nested": {"password": "secret"},
            "items": [{"source_text": "private list item", "authorization": "Bearer secret"}],
            "status": "ok",
        },
    )
    assert telemetry.records[0]["attributes"]["content"] == "[REDACTED]"
    assert telemetry.records[0]["attributes"]["nested"]["password"] == "[REDACTED]"
    assert telemetry.records[0]["attributes"]["items"][0]["source_text"] == "[REDACTED]"
    assert telemetry.records[0]["attributes"]["items"][0]["authorization"] == "[REDACTED]"


def test_local_agent_writes_bounded_run_checkpoint(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'checkpoint-run.db'}",
        object_store_path=tmp_path / "objects",
    )
    api = TestClient(create_app(settings))
    project = api.post(
        "/v1/projects",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
        json={"name": "Checkpointed", "project_type": "brief", "brief": "Checkpoint state"},
    ).json()
    response = api.post(
        f"/v1/projects/{project['id']}/threads/messages",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
        json={"text": "Answer from the project state"},
    )
    assert response.status_code == 202
    detail = api.get(
        f"/v1/projects/{project['id']}",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
    ).json()
    checkpoint = load_checkpoint(settings, "local-workspace", project["id"], detail["thread_id"])
    assert checkpoint is not None
    assert checkpoint["run_id"] == response.json()["id"]
    assert checkpoint["status"] == "completed"
    assert "request_text" not in checkpoint


def test_concurrent_checkpoint_writers_leave_complete_json(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'checkpoint-concurrency.db'}",
        object_store_path=tmp_path / "objects",
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda index: save_checkpoint(
                    settings,
                    "workspace-a",
                    "project-a",
                    "thread-a",
                    {"writer": index, "status": "completed"},
                ),
                range(32),
            )
        )
    checkpoint = load_checkpoint(settings, "workspace-a", "project-a", "thread-a")
    assert checkpoint is not None
    assert checkpoint["status"] == "completed"


def test_outbox_delivery_marks_only_successful_messages(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'outbox.db'}")
    init_database(settings.database_url)
    session = build_session_factory(settings.database_url)()
    session.add(
        OutboxMessage(
            id=new_id("evt"),
            workspace_id="local-workspace",
            event_type="TestEvent",
            aggregate_type="project",
            aggregate_id="project-1",
            payload={"safe": True},
        )
    )
    session.commit()
    delivered = []
    assert publish_pending(session, delivered.append) == 1
    assert delivered[0]["event_type"] == "TestEvent"
    assert publish_pending(session, delivered.append) == 0
    session.close()
