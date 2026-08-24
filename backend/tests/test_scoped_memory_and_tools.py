from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.tools.typed import TOOL_REGISTRY
from fastapi.testclient import TestClient


def test_primary_registry_excludes_canonical_commit_commands():
    names = {tool.name for tool in TOOL_REGISTRY.values()}
    assert "accept_patch" not in names
    assert "publish_skill" not in names
    assert all(tool.mode in {"read", "proposal"} for tool in TOOL_REGISTRY.values())


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

