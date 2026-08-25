from app.config import Settings
from app.context import RuntimeContext
from app.main import create_app
from app.models import DelegatedTask, SkillVersion
from app.services import run_delegated_worker_once
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
        with app.state.session_factory() as db:
            result = run_delegated_worker_once(
                db,
                RuntimeContext("local-user", "local-workspace", frozenset({"workspace_admin"}), "delegated-test"),
                "delegated-test-worker",
            )
            assert result == {"claimed": 1, "completed": 1, "cancelled": 0, "failed": 0}
            assert db.query(DelegatedTask).filter_by(id=task_id).one().status == "completed"


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


def test_skill_repair_creates_immutable_version_then_validates_and_publishes(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'skill-repair.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with TestClient(app) as api:
        draft = api.post(
            "/v1/skills",
            headers=headers(),
            json={
                "slug": "repairable-skill",
                "name": "Repairable skill",
                "description": "A package that needs review",
                "content": "curl http://untrusted.example",
            },
        )
        assert draft.status_code == 201
        original_id = draft.json()["id"]
        invalid = api.post(
            f"/v1/skill-versions/{original_id}/validate", headers=headers()
        )
        assert invalid.status_code == 422

        repaired = api.put(
            f"/v1/skill-versions/{original_id}/repair",
            headers={**headers(), "Idempotency-Key": "repair-once"},
            json={
                "description": "A safe reviewed package",
                "content": "Use source evidence and keep changes reviewable.",
            },
        )
        assert repaired.status_code == 201
        assert repaired.json()["status"] == "draft"
        assert repaired.json()["id"] != original_id
        replay = api.put(
            f"/v1/skill-versions/{original_id}/repair",
            headers={**headers(), "Idempotency-Key": "repair-once"},
            json={
                "description": "A different payload must not create a second version",
                "content": "ignored on idempotent replay",
            },
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == repaired.json()["id"]
        valid = api.post(
            f"/v1/skill-versions/{repaired.json()['id']}/validate", headers=headers()
        )
        assert valid.status_code == 200
        assert valid.json()["status"] == "valid"
        published = api.post(
            f"/v1/skill-versions/{repaired.json()['id']}/publish", headers=headers()
        )
        assert published.status_code == 200
        assert published.json()["status"] == "published"
        with app.state.session_factory() as db:
            versions = (
                db.query(SkillVersion)
                .filter_by(skill_id=repaired.json()["skill_id"])
                .order_by(SkillVersion.version_no)
                .all()
            )
            assert [version.version_no for version in versions] == [1, 2]
            assert versions[0].status == "invalid"


def test_published_starter_skill_can_be_forked_into_scoped_workspace_draft(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'skill-fork.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    with TestClient(app) as api:
        starter = next(
            skill
            for skill in api.get("/v1/skills", headers=headers()).json()
            if skill["scope"] == "starter"
        )
        forked = api.post(
            f"/v1/skills/{starter['id']}/fork",
            headers={**headers(), "Idempotency-Key": "fork-once"},
            json={"slug": "forked-starter"},
        )
        assert forked.status_code == 201
        assert forked.json()["scope"] == "workspace"
        assert forked.json()["status"] == "draft"
        replay = api.post(
            f"/v1/skills/{starter['id']}/fork",
            headers={**headers(), "Idempotency-Key": "fork-once"},
            json={"slug": "different-slug"},
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == forked.json()["id"]
