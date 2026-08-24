from app.config import Settings
from app.main import create_app
from app.models import DelegatedTask
from fastapi.testclient import TestClient


def headers():
    return {
        "X-User-ID": "local-user",
        "X-Workspace-ID": "local-workspace",
    }


def test_partial_delegation_retry_is_bounded_and_reconciled(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'delegation.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with TestClient(app) as api:
        project = api.post(
            "/v1/projects",
            headers=headers(),
            json={"name": "Delegation", "project_type": "brief", "brief": "Reconcile tasks"},
        ).json()
        run = api.post(
            f"/v1/projects/{project['id']}/threads/messages",
            headers=headers(),
            json={"text": "Generate a draft"},
        ).json()
        with app.state.session_factory() as db:
            task = db.query(DelegatedTask).filter_by(parent_run_id=run["id"]).first()
            assert task is not None
            task.status = "failed"
            task.error_code = "WORKER_DIED"
            db.commit()
            task_id = task.id
        retry = api.post(f"/v1/delegated-tasks/{task_id}/retry", headers=headers())
        assert retry.status_code == 200
        assert retry.json()["status"] == "queued"
        retry_again = api.post(f"/v1/delegated-tasks/{task_id}/retry", headers=headers())
        assert retry_again.status_code == 200
        assert retry_again.json()["attempts"] == 1
        summary = api.post(
            f"/v1/runs/{run['id']}/delegated-tasks/reconcile", headers=headers()
        )
        assert summary.status_code == 200
        assert summary.json()["counts"]["queued"] == 1


def test_skill_author_endpoint_creates_draft_only_and_provider_failure_is_explicit(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'skill-author.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with TestClient(app) as api:
        draft = api.post(
            "/v1/skills/ai-drafts",
            headers=headers(),
            json={"objective": "Review safety guidance", "suggested_name": "Safety review"},
        )
        assert draft.status_code == 201
        assert draft.json()["status"] == "draft"
        assert api.post(
            f"/v1/skill-versions/{draft.json()['id']}/publish", headers=headers()
        ).status_code == 409

    provider_settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'skill-provider.db'}",
        object_store_path=tmp_path / "provider-objects",
        model_provider="openai",
    )
    with TestClient(create_app(provider_settings)) as api:
        unavailable = api.post(
            "/v1/skills/ai-drafts",
            headers=headers(),
            json={"objective": "Provider-authored skill"},
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["retryable"] is True
