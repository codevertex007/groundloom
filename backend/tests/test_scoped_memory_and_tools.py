from pathlib import Path

from app.ai.tools.catalog import TOOL_CATALOG
from app.config import Settings
from app.context import RuntimeContext
from app.integrations.ai.services import GroundloomAgentServices
from app.main import create_app
from fastapi.testclient import TestClient


def test_primary_registry_excludes_canonical_commit_commands():
    names = {tool.name for tool in TOOL_CATALOG.values()}
    assert "accept_patch" not in names
    assert "publish_skill" not in names
    assert all(tool.mode in {"read", "proposal"} for tool in TOOL_CATALOG.values())


def test_memory_is_scoped_and_secret_rejected(tmp_path: Path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'memory.db'}", object_store_path=tmp_path / "objects"))
    api = TestClient(app)
    headers = {"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"}
    saved = api.post("/v1/memory", headers=headers, json={"namespace": "preferences", "key": "style", "value": {"tone": "concise"}})
    assert saved.status_code == 200
    assert api.get("/v1/memory", headers=headers).json()[0]["value"]["tone"] == "concise"
    denied = api.post("/v1/memory", headers={**headers, "X-Workspace-ID": "other"}, json={"namespace": "preferences", "key": "x", "value": {}})
    assert denied.status_code == 403
    secret = api.post("/v1/memory", headers=headers, json={"namespace": "preferences", "key": "secret", "value": {"api_key": "do-not-store"}})
    assert secret.status_code == 422


def test_agent_patch_idempotency_fingerprints_the_complete_bounded_request(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'agent-patches.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    headers = {"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"}
    with TestClient(app) as api:
        project = api.post(
            "/v1/projects",
            headers=headers,
            json={"name": "Patch keys", "project_type": "brief", "brief": "Key patches safely"},
        ).json()

    context = RuntimeContext(
        "local-user",
        "local-workspace",
        frozenset({"workspace_admin"}),
        "patch-key-test",
    )
    with app.state.session_factory() as db:
        services = GroundloomAgentServices(db, context, project["id"], settings)
        first = services.propose_text_patch("Same summary", "First proposed text")
        replay = services.propose_text_patch("Same summary", "First proposed text")
        second = services.propose_text_patch("Same summary", "Different proposed text")

    assert replay == first
    assert second["patch_id"] != first["patch_id"]
