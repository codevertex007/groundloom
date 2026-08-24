import json

import pytest
from app.agent_runtime import LocalDeterministicAgentRuntime, build_agent_runtime
from app.checkpoints import load_checkpoint, save_checkpoint
from app.config import Settings
from app.db import build_session_factory, init_database
from app.errors import GroundloomError
from app.ids import new_id
from app.main import create_app
from app.models import OutboxMessage
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
    json.dumps(schema)


def test_checkpoint_scope_and_redacted_telemetry(tmp_path):
    settings = Settings(object_store_path=tmp_path / "objects")
    save_checkpoint(settings, "workspace", "project", "thread", {"cursor": 3})
    assert load_checkpoint(settings, "workspace", "project", "thread") == {"cursor": 3}
    with pytest.raises(GroundloomError):
        save_checkpoint(settings, "workspace/other", "project", "thread", {})
    telemetry = build_telemetry("local")
    assert isinstance(telemetry, LocalTelemetry)
    telemetry.emit(
        "test", {"content": "private", "nested": {"password": "secret"}, "status": "ok"}
    )
    assert telemetry.records[0]["attributes"]["content"] == "[REDACTED]"
    assert telemetry.records[0]["attributes"]["nested"]["password"] == "[REDACTED]"


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
