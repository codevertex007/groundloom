from app.auth import issue_context_token
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_signed_identity_controls_workspace_context(tmp_path):
    settings = Settings(
        env="staging",
        auth_mode="hmac",
        auth_secret="test-secret",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        object_store_path=tmp_path / "objects",
    )
    api = TestClient(create_app(settings))
    assert api.get("/v1/projects").status_code == 401
    token = issue_context_token("local-user", "local-workspace", settings.auth_secret)
    response = api.get(
        "/v1/projects",
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-ID": "attacker",
            "X-Workspace-ID": "other-workspace",
        },
    )
    assert response.status_code == 200
    assert api.get("/v1/projects", headers={"Authorization": f"Bearer {token[:-1]}x"}).status_code == 401
