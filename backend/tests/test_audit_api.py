from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.models import Membership
from fastapi.testclient import TestClient


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'audit.db'}",
        object_store_path=tmp_path / "objects",
    )
    return TestClient(create_app(settings))


def _headers(**overrides: str) -> dict[str, str]:
    result = {
        "X-User-ID": "local-user",
        "X-Workspace-ID": "local-workspace",
        "X-Correlation-ID": "audit-test",
    }
    result.update(overrides)
    return result


def test_audit_api_is_admin_only_bounded_and_cursor_paginated(tmp_path: Path):
    api = _client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=_headers(),
        json={"name": "Audited", "project_type": "brief", "brief": "Audit evidence"},
    )
    assert project.status_code == 201
    preferences = api.put(
        "/v1/workspace/preferences",
        headers=_headers(),
        json={"default_export": "md", "require_citations": True},
    )
    assert preferences.status_code == 200

    first = api.get("/v1/audit-events?limit=1", headers=_headers())
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "workspace.preferences.updated"
    assert body["items"][0]["summary"]
    assert "payload" not in body["items"][0]

    actions = [body["items"][0]["action"]]
    seen_ids = {body["items"][0]["id"]}
    cursor = body["next_cursor"]
    while cursor:
        page = api.get(f"/v1/audit-events?limit=1&cursor={cursor}", headers=_headers())
        assert page.status_code == 200, page.text
        item = page.json()["items"][0]
        assert item["id"] not in seen_ids
        seen_ids.add(item["id"])
        actions.append(item["action"])
        cursor = page.json()["next_cursor"]
    assert "project.created" in actions

    read_event = api.get("/v1/audit-events?limit=1", headers=_headers())
    assert read_event.status_code == 200
    assert read_event.json()["items"][0]["action"] == "audit.read"

    invalid = api.get("/v1/audit-events?cursor=not-a-cursor", headers=_headers())
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_CURSOR"

    with api.app.state.session_factory() as db:
        membership = (
            db.query(Membership)
            .filter_by(user_id="local-user", workspace_id="local-workspace")
            .one()
        )
        membership.role = "author"
        db.commit()
    denied = api.get("/v1/audit-events", headers=_headers())
    assert denied.status_code == 403
    assert denied.json()["code"] == "PERMISSION_DENIED"
