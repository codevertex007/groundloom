import base64
from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'groundloom.db'}",
        object_store_path=tmp_path / "objects",
    )
    return TestClient(create_app(settings))


def headers(**overrides):
    result = {
        "X-User-ID": "local-user",
        "X-Workspace-ID": "local-workspace",
        "X-Correlation-ID": "test-correlation",
    }
    result.update(overrides)
    return result


def test_project_source_grounded_run_and_replay(tmp_path):
    api = client(tmp_path)
    raw = base64.b64encode(b"Torque guidance\n\nUse 10 Nm for the service fastener.").decode()
    source = api.post(
        "/v1/sources/uploads",
        headers=headers(),
        json={
            "name": "Service guide",
            "filename": "guide.txt",
            "content_base64": raw,
            "mime_type": "text/plain",
        },
    )
    assert source.status_code == 201, source.text
    source_version_id = source.json()["current_version_id"]
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "Torque brief",
            "project_type": "brief",
            "brief": "Explain torque guidance",
            "source_version_ids": [source_version_id],
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    detail = api.get(f"/v1/projects/{project_id}", headers=headers())
    assert detail.status_code == 200
    thread_id = detail.json()["thread_id"]
    run = api.post(
        f"/v1/projects/{project_id}/threads/messages",
        headers=headers(**{"Idempotency-Key": "generate-1"}),
        json={"text": "Generate a cited draft about torque guidance"},
    )
    assert run.status_code == 202, run.text
    events = api.get(f"/v1/threads/{thread_id}/events", headers=headers())
    assert events.status_code == 200
    types = [item["type"] for item in events.json()]
    assert "run.started" in types and "patch.proposed" in types and "run.completed" in types
    stream = api.get(f"/v1/threads/{thread_id}/events/stream", headers=headers())
    assert stream.status_code == 200 and "event: run.started" in stream.text
    replay = api.get(
        f"/v1/threads/{thread_id}/events",
        headers=headers(**{"Last-Event-ID": events.json()[2]["event_id"]}),
    )
    assert all(item["seq"] > events.json()[2]["seq"] for item in replay.json())


def test_project_create_is_idempotent(tmp_path):
    api = client(tmp_path)
    payload = {"name": "Retry safe", "project_type": "brief", "brief": "Create once"}
    first = api.post("/v1/projects", headers=headers(**{"Idempotency-Key": "project-1"}), json=payload)
    second = api.post("/v1/projects", headers=headers(**{"Idempotency-Key": "project-1"}), json=payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_plan_approval_interrupt_resumes_same_run_and_thread(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "Approval flow",
            "project_type": "brief",
            "brief": "A reviewable plan",
            "defaults": {"require_plan_approval": True},
        },
    ).json()
    run_response = api.post(
        f"/v1/projects/{project['id']}/threads/messages",
        headers=headers(**{"Idempotency-Key": "approval-run-1"}),
        json={"text": "Generate a draft after plan approval"},
    )
    assert run_response.status_code == 202
    run = run_response.json()
    assert run["status"] == "waiting_for_approval"
    assert run["budget"]["max_estimated_tokens"] == 12000
    assert run["usage"]["tool_calls"] == 1
    approvals = api.get(f"/v1/runs/{run['id']}/approvals", headers=headers())
    assert approvals.status_code == 200 and len(approvals.json()) == 1
    approval = approvals.json()[0]
    assert approval["status"] == "pending"
    resolved = api.post(
        f"/v1/approvals/{approval['id']}/resolve",
        headers=headers(),
        json={"decision": "approved", "reason": "Plan matches the brief."},
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "approved"
    resumed = api.get(f"/v1/runs/{run['id']}", headers=headers()).json()
    assert resumed["status"] == "completed"
    assert resumed["thread_id"] == run["thread_id"]
    event_types = [
        event["type"]
        for event in api.get(
            f"/v1/threads/{run['thread_id']}/events", headers=headers()
        ).json()
    ]
    assert "approval.required" in event_types
    assert "approval.resolved" in event_types
    assert event_types.count("patch.proposed") == 1


def test_local_agent_trajectory_skips_delegation_for_initialization(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Trajectory", "project_type": "brief", "brief": "A trajectory"},
    ).json()
    run = api.post(
        f"/v1/projects/{project['id']}/threads/messages",
        headers=headers(**{"Idempotency-Key": "trajectory-initialize"}),
        json={"text": "initialize"},
    )
    assert run.status_code == 202
    detail = api.get(f"/v1/projects/{project['id']}", headers=headers()).json()
    events = api.get(f"/v1/threads/{detail['thread_id']}/events", headers=headers()).json()
    event_types = [event["type"] for event in events]
    assert "run.completed" in event_types
    assert "subagent.completed" not in event_types


def test_source_revision_is_immutable_and_keeps_lineage(tmp_path):
    api = client(tmp_path)
    first = base64.b64encode(b"First approved guidance.").decode()
    source = api.post(
        "/v1/sources/uploads",
        headers=headers(),
        json={"name": "Revision guide", "filename": "guide.txt", "content_base64": first},
    )
    assert source.status_code == 201
    source_id = source.json()["id"]
    first_version = source.json()["current_version_id"]
    second = api.post(
        f"/v1/sources/{source_id}/versions",
        headers=headers(),
        json={
            "name": "Ignored lineage name",
            "filename": "guide.txt",
            "content_base64": base64.b64encode(b"Second approved guidance.").decode(),
        },
    )
    assert second.status_code == 201
    assert second.json()["id"] == source_id
    assert second.json()["current_version_id"] != first_version
    assert sorted(item["version_no"] for item in second.json()["versions"]) == [1, 2]
    wrong_type = api.post(
        f"/v1/sources/{source_id}/versions",
        headers=headers(),
        json={"name": "Revision guide", "filename": "guide.md", "content_base64": first},
    )
    assert wrong_type.status_code == 422


def test_patch_reject_and_accept_exactly_once(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Reviewable", "project_type": "brief", "brief": "A reviewable brief"},
    ).json()
    project_id = project["id"]
    api.post(
        f"/v1/projects/{project_id}/threads/messages",
        headers=headers(),
        json={"text": "Generate a draft"},
    )
    patches = api.get(f"/v1/projects/{project_id}/patches", headers=headers()).json()
    patch = patches[0]
    base = patch["base_content_version_id"]
    rejected = api.post(
        f"/v1/patches/{patch['id']}/reject",
        headers=headers(),
        json={"expected_current_version_id": base, "reason": "Not needed"},
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    content_before = api.get(f"/v1/projects/{project_id}/content", headers=headers()).json()
    assert content_before["version"]["id"] == base

    api.post(
        f"/v1/projects/{project_id}/threads/messages",
        headers=headers(),
        json={"text": "Generate another draft"},
    )
    patch = api.get(f"/v1/projects/{project_id}/patches", headers=headers()).json()[0]
    accepted = api.post(
        f"/v1/patches/{patch['id']}/accept",
        headers=headers(),
        json={"expected_current_version_id": patch["base_content_version_id"]},
    )
    assert accepted.status_code == 200
    accepted_again = api.post(
        f"/v1/patches/{patch['id']}/accept",
        headers=headers(),
        json={"expected_current_version_id": accepted.json()["base_content_version_id"]},
    )
    assert accepted_again.status_code == 200
    content_after = api.get(f"/v1/projects/{project_id}/content", headers=headers()).json()
    assert content_after["version"]["id"] != base


def test_cross_workspace_is_denied(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Private", "project_type": "brief", "brief": "Private"},
    ).json()
    denied = api.get(
        f"/v1/projects/{project['id']}", headers=headers(**{"X-Workspace-ID": "other-workspace"})
    )
    assert denied.status_code == 403


def test_skill_publish_validation_and_export(tmp_path):
    api = client(tmp_path)
    skill = api.post(
        "/v1/skills",
        headers=headers(),
        json={
            "slug": "review-style",
            "name": "Review style",
            "description": "Review concise drafts",
            "content": "Cite every factual claim.",
        },
    )
    assert skill.status_code == 201
    version_id = skill.json()["id"]
    assert (
        api.post(f"/v1/skill-versions/{version_id}/validate", headers=headers()).status_code == 200
    )
    assert (
        api.post(f"/v1/skill-versions/{version_id}/publish", headers=headers()).status_code == 200
    )
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Exportable", "project_type": "brief", "brief": "Export this"},
    ).json()
    content = api.get(f"/v1/projects/{project['id']}/content", headers=headers()).json()
    export = api.post(
        "/v1/exports",
        headers=headers(),
        json={
            "project_id": project["id"],
            "content_version_id": content["version"]["id"],
            "format": "pdf",
        },
    )
    assert export.status_code == 202 and export.json()["status"] == "completed"
    download = api.get(f"/v1/exports/{export.json()['id']}/download", headers=headers())
    assert download.status_code == 200 and download.content.startswith(b"%PDF")
