from app.auth import issue_context_token
from app.config import Settings
from app.db import set_tenant_context, set_worker_context
from app.main import create_app
from app.migrations import _RLS_WORKSPACE_TABLES, _apply_postgres_rls
from app.models import AgentRun
from fastapi.testclient import TestClient


def test_session_tenant_context_is_explicit_and_worker_context_is_distinct(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'context.db'}")
    app = create_app(settings)
    with app.state.session_factory() as db:
        set_tenant_context(db, "workspace-a")
        assert db.info["workspace_id"] == "workspace-a"
        assert "service_role" not in db.info
        set_worker_context(db)
        assert db.info["service_role"] == "worker"


def test_postgres_rls_migration_generates_forced_workspace_policies():
    class FakeConnection:
        def __init__(self):
            self.statements = []

        def exec_driver_sql(self, statement):
            self.statements.append(statement)

    connection = FakeConnection()
    _apply_postgres_rls(connection)
    assert len(connection.statements) == len(_RLS_WORKSPACE_TABLES) * 4
    assert any(
        "ALTER TABLE projects FORCE ROW LEVEL SECURITY" in statement
        for statement in connection.statements
    )
    create_policies = [
        statement for statement in connection.statements if statement.startswith("CREATE POLICY")
    ]
    assert len(create_policies) == len(_RLS_WORKSPACE_TABLES)
    assert all("current_setting('app.workspace_id', true)" in statement for statement in create_policies)
    assert all("current_user = 'groundloom_worker'" in statement for statement in create_policies)


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


def test_configured_provider_failure_is_retryable_and_never_local_success(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'provider-failure.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with TestClient(app) as api:
        project = api.post(
            "/v1/projects",
            headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
            json={"name": "Provider failure", "project_type": "brief", "brief": "Failure"},
        ).json()
        settings.model_provider = "openai"
        settings.checkpoint_backend = "postgres"
        response = api.post(
            f"/v1/projects/{project['id']}/threads/messages",
            headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
            json={"text": "Generate with the configured provider"},
        )
        assert response.status_code == 503
        assert response.json()["retryable"] is True
        with app.state.session_factory() as db:
            run = db.query(AgentRun).filter_by(project_id=project["id"], status="failed").one()
            assert run.status == "failed"
