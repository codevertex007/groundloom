import base64
from pathlib import Path

import pytest
from app.auth import issue_context_token
from app.checkpoints import PostgresCheckpointProvider, build_checkpoint_provider
from app.config import Settings
from app.context import RuntimeContext
from app.errors import GroundloomError
from app.main import create_app
from app.models import AgentRun, IngestionJob, SourceVersion
from app.object_store import LocalObjectStore, S3ObjectStore
from app.services import run_agent_worker_once, run_ingestion_worker_once
from app.telemetry import LangfuseTelemetry
from fastapi.testclient import TestClient
from scripts.backup_local import build_manifest, copy_tree, verify_manifest


def test_local_object_store_rejects_escape_and_round_trips(tmp_path: Path):
    store = LocalObjectStore(tmp_path / "objects")
    store.put_bytes("workspace/source.txt", b"evidence")
    assert store.get_bytes("workspace/source.txt") == b"evidence"
    assert store.exists("workspace/source.txt")
    with pytest.raises(GroundloomError):
        store.put_bytes("../outside.txt", b"blocked")


def test_external_adapters_classify_outages_without_leaking_provider_errors():
    class FakeClient:
        def __init__(self, code):
            self.code = code

        def get_object(self, **_kwargs):
            error = RuntimeError("provider secret should not escape")
            error.response = {"Error": {"Code": self.code}}
            raise error

    missing = object.__new__(S3ObjectStore)
    missing.bucket = "test"
    missing.client = FakeClient("NoSuchKey")
    with pytest.raises(GroundloomError) as missing_error:
        missing.get_bytes("missing.bin")
    assert missing_error.value.code == "RESOURCE_NOT_FOUND"
    outage = object.__new__(S3ObjectStore)
    outage.bucket = "test"
    outage.client = FakeClient("AccessDenied")
    with pytest.raises(GroundloomError) as outage_error:
        outage.get_bytes("artifact.bin")
    assert outage_error.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage_error.value.retryable is True

    class FailingTelemetry:
        def create_event(self, **_kwargs):
            raise RuntimeError("telemetry credentials")

        def flush(self):
            raise RuntimeError("telemetry unavailable")

    telemetry = object.__new__(LangfuseTelemetry)
    telemetry.client = FailingTelemetry()
    telemetry.dropped_events = 0
    telemetry.last_error_class = None
    telemetry.emit("test", {"safe": True})
    telemetry.flush()
    assert telemetry.dropped_events == 2
    assert telemetry.last_error_class == "RuntimeError"


def test_production_requires_postgres_checkpoint_and_s3_storage():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        model_provider="openai",
        telemetry_provider="langfuse",
        object_store_backend="s3",
        object_store_bucket="groundloom",
        checkpoint_backend="postgres",
        auth_secret="local-test-secret-that-is-at-least-32-chars",
        auth_mode="hmac",
        public_base_url="https://groundloom.example",
        cors_origins=["https://app.groundloom.example"],
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_host="https://langfuse.example",
        agent_inline_local=False,
    )
    settings.validate_runtime()
    assert isinstance(build_checkpoint_provider(settings), PostgresCheckpointProvider)


def test_production_rejects_weak_identity_and_local_domains():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        model_provider="openai",
        telemetry_provider="langfuse",
        object_store_backend="s3",
        object_store_bucket="groundloom",
        checkpoint_backend="postgres",
        auth_secret="too-short",
        auth_mode="hmac",
        public_base_url="http://localhost:8000",
        agent_inline_local=False,
    )
    with pytest.raises(RuntimeError, match="at least 32"):
        settings.validate_runtime()


def test_upload_creates_completed_ingestion_job(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    response = api.post(
        "/v1/sources/uploads",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
        json={
            "name": "Job source",
            "filename": "job.txt",
            "content_base64": base64.b64encode(b"Queued source content.").decode(),
        },
    )
    assert response.status_code == 201
    source_version_id = response.json()["current_version_id"]
    with app.state.session_factory() as db:
        version = db.get(SourceVersion, source_version_id)
        job = db.query(IngestionJob).filter_by(source_version_id=source_version_id).one()
        assert version.status == "ready"
        assert job.status == "completed"
        assert job.stage == "ready"


def test_ingestion_worker_reclaims_and_replays_a_queued_job(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    response = api.post(
        "/v1/sources/uploads",
        json={
            "name": "Worker source",
            "filename": "worker.txt",
            "mime_type": "text/plain",
            "content_base64": base64.b64encode(b"durable worker evidence").decode(),
        },
    )
    assert response.status_code == 201
    with app.state.session_factory() as db:
        job = db.query(IngestionJob).one()
        version = db.query(SourceVersion).one()
        job.status = "queued"
        job.stage = "queued"
        job.lease_owner = None
        job.lease_until = None
        version.status = "uploaded"
        db.commit()
        ctx = RuntimeContext(
            settings.local_user_id,
            settings.local_workspace_id,
            frozenset({"workspace_admin"}),
            "corr-worker-test",
        )
        result = run_ingestion_worker_once(db, ctx, settings, "worker-test")
        assert result == {"claimed": 1, "completed": 1, "failed": 0}
        assert db.query(IngestionJob).one().attempts == 1
        assert db.query(SourceVersion).one().status == "ready"


def test_parser_rejects_mime_spoofed_docx_and_persists_failure(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'parser.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    response = api.post(
        "/v1/sources/uploads",
        json={
            "name": "Spoofed document",
            "filename": "spoof.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_base64": base64.b64encode(b"not a zip").decode(),
        },
    )
    assert response.status_code == 422
    with app.state.session_factory() as db:
        assert db.query(IngestionJob).one().status == "failed"
        assert db.query(SourceVersion).one().failure_code == "PARSE_FAILED"


def test_local_backup_manifest_verifies_database_and_objects(tmp_path: Path):
    database = tmp_path / "groundloom.db"
    objects = tmp_path / "objects"
    objects.mkdir()
    database.write_bytes(b"sqlite fixture")
    (objects / "workspace" ).mkdir()
    (objects / "workspace" / "artifact.bin").write_bytes(b"artifact")
    backup = tmp_path / "backup"
    backup.mkdir()
    backup_database = backup / "groundloom.db"
    backup_objects = backup / "objects"
    backup_database.write_bytes(database.read_bytes())
    copy_tree(objects, backup_objects)
    manifest = build_manifest(backup_database, backup_objects)
    restored = tmp_path / "restored"
    restored.mkdir()
    restored_database = restored / "groundloom.db"
    restored_objects = restored / "objects"
    restored_database.write_bytes(backup_database.read_bytes())
    copy_tree(backup_objects, restored_objects)
    verify_manifest(restored_database, restored_objects, manifest)


def test_agent_worker_claims_queued_runs_and_preserves_inline_local_mode(tmp_path: Path):
    settings = Settings(
        env="staging",
        auth_mode="hmac",
        auth_secret="staging-test-secret-that-is-long-enough",
        database_url=f"sqlite:///{tmp_path / 'agent-worker.db'}",
        object_store_path=tmp_path / "objects",
        agent_inline_local=False,
    )
    app = create_app(settings)
    token = issue_context_token("local-user", "local-workspace", settings.auth_secret)
    headers = {"Authorization": f"Bearer {token}"}
    api = TestClient(app)
    project = api.post(
        "/v1/projects",
        headers=headers,
        json={"name": "Queued agent", "project_type": "brief", "brief": "Worker-backed run"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    message = api.post(
        f"/v1/projects/{project_id}/threads/messages",
        headers=headers,
        json={"text": "initialize"},
    )
    assert message.status_code == 202 and message.json()["status"] == "queued"
    with app.state.session_factory() as db:
        result = run_agent_worker_once(db, settings, "agent-test-worker", limit=10)
        assert result == {"claimed": 2, "completed": 2, "requeued": 0, "failed": 0}
        assert all(run.status == "completed" for run in db.query(AgentRun).all())
