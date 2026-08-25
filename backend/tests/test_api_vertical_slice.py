import base64
from pathlib import Path
from urllib.parse import urlparse

from app.auth import issue_context_token
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
    evidence = api.get(
        f"/v1/projects/{project_id}/sources/search?q=torque guidance",
        headers=headers(),
    )
    assert evidence.status_code == 200
    assert evidence.json()["retrieval_version"] == "hybrid.v2"
    assert evidence.json()["passages"]
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


def test_project_page_is_bounded_cursor_scoped_and_rejects_invalid_cursor(tmp_path):
    api = client(tmp_path)
    created = []
    for index in range(3):
        response = api.post(
            "/v1/projects",
            headers=headers(**{"Idempotency-Key": f"page-project-{index}"}),
            json={"name": f"Page project {index}", "project_type": "brief", "brief": "Page me"},
        )
        assert response.status_code == 201
        created.append(response.json()["id"])

    first = api.get("/v1/projects/page?limit=2", headers=headers())
    assert first.status_code == 200
    first_page = first.json()
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"]

    second = api.get(
        f"/v1/projects/page?limit=2&cursor={first_page['next_cursor']}",
        headers=headers(),
    )
    assert second.status_code == 200
    second_page = second.json()
    assert len(second_page["items"]) == 1
    assert second_page["next_cursor"] is None
    assert {item["id"] for item in first_page["items"] + second_page["items"]} == set(created)

    invalid = api.get("/v1/projects/page?cursor=not-a-cursor", headers=headers())
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_CURSOR"
    other_workspace = api.get(
        "/v1/projects/page", headers=headers(**{"X-Workspace-ID": "other-workspace"})
    )
    assert other_workspace.status_code == 403


def test_project_pins_selected_published_skill_version(tmp_path):
    api = client(tmp_path)
    skill = api.post(
        "/v1/skills",
        headers=headers(),
        json={
            "slug": "project-skill",
            "name": "Project skill",
            "description": "A project-specific guidance package",
            "content": "Use selected evidence and cite factual claims.",
        },
    )
    assert skill.status_code == 201
    version_id = skill.json()["id"]
    assert api.post(
        f"/v1/skill-versions/{version_id}/validate", headers=headers()
    ).status_code == 200
    assert api.post(
        f"/v1/skill-versions/{version_id}/publish", headers=headers()
    ).status_code == 200
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "Skill-pinned project",
            "project_type": "brief",
            "brief": "Use the selected project skill.",
            "skill_version_ids": [version_id],
        },
    )
    assert project.status_code == 201
    detail = api.get(f"/v1/projects/{project.json()['id']}", headers=headers())
    assert detail.status_code == 200
    assert detail.json()["config"]["skill_version_ids"] == [version_id]


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
        headers=headers(**{"Idempotency-Key": "approval-decision-1"}),
        json={"decision": "approved", "reason": "Plan matches the brief."},
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "approved"
    replay = api.post(
        f"/v1/approvals/{approval['id']}/resolve",
        headers=headers(**{"Idempotency-Key": "approval-decision-1"}),
        json={"decision": "approved", "reason": "A different retry payload."},
    )
    assert replay.status_code == 200 and replay.json() == resolved.json()
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


def test_queued_run_can_be_cancelled_and_replayed_without_resuming(tmp_path):
    settings = Settings(
        env="staging",
        auth_mode="hmac",
        auth_secret="staging-test-secret-that-is-long-enough",
        database_url=f"sqlite:///{tmp_path / 'cancel.db'}",
        object_store_path=tmp_path / "objects",
        agent_inline_local=False,
    )
    api = TestClient(create_app(settings))
    token = issue_context_token("local-user", "local-workspace", settings.auth_secret)
    auth_headers = {"Authorization": f"Bearer {token}"}
    project = api.post(
        "/v1/projects",
        headers=auth_headers,
        json={"name": "Cancellable run", "project_type": "brief", "brief": "Cancel safely"},
    ).json()
    run_id = project["current_run_id"]
    queued = api.get(f"/v1/runs/{run_id}", headers=auth_headers)
    assert queued.status_code == 200 and queued.json()["status"] == "queued"
    concurrent = api.post(
        f"/v1/projects/{project['id']}/threads/messages",
        headers={**auth_headers, "Idempotency-Key": "cancel-run-2"},
        json={"text": "Race this draft"},
    )
    assert concurrent.status_code == 409
    assert concurrent.json()["code"] == "INVALID_STATE"
    cancelled = api.post(f"/v1/runs/{run_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    replay = api.post(f"/v1/runs/{run_id}/cancel", headers=auth_headers)
    assert replay.status_code == 200 and replay.json()["status"] == "cancelled"


def test_workspace_preferences_are_typed_audited_pinned_and_idempotent(tmp_path):
    api = client(tmp_path)
    initial = api.get("/v1/workspace/preferences", headers=headers())
    assert initial.status_code == 200
    assert initial.json()["version_no"] == 1
    updated = api.put(
        "/v1/workspace/preferences",
        headers=headers(**{"Idempotency-Key": "workspace-prefs-1"}),
        json={
            "review_ai_edits": True,
            "require_citations": False,
            "default_export": "md",
            "require_plan_approval": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version_no"] == 2
    replay = api.put(
        "/v1/workspace/preferences",
        headers=headers(**{"Idempotency-Key": "workspace-prefs-1"}),
        json={"default_export": "pdf"},
    )
    assert replay.status_code == 200 and replay.json() == updated.json()
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Pinned preferences", "project_type": "brief", "brief": "Uses workspace defaults"},
    )
    assert project.status_code == 201
    detail = api.get(f"/v1/projects/{project.json()['id']}", headers=headers()).json()
    assert detail["config"]["defaults"]["require_plan_approval"] is True
    assert detail["config"]["defaults"]["default_export"] == "md"


def test_run_budget_stops_optional_work_with_durable_waiting_state(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "Budgeted run",
            "project_type": "brief",
            "brief": "Budget boundary",
            "defaults": {"max_estimated_tokens": 5},
        },
    ).json()
    run = api.post(
        f"/v1/projects/{project['id']}/threads/messages",
        headers=headers(**{"Idempotency-Key": "budget-run-1"}),
        json={"text": "Generate a draft that must stop at the configured budget"},
    )
    assert run.status_code == 202
    assert run.json()["status"] == "waiting_for_user"
    assert run.json()["error_code"] == "BUDGET_EXCEEDED"
    detail = api.get(f"/v1/projects/{project['id']}", headers=headers()).json()
    events = api.get(f"/v1/threads/{detail['thread_id']}/events", headers=headers()).json()
    assert any(event["type"] == "budget.stopped" for event in events)


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
    download_url = urlparse(export.json()["download_url"])
    download = api.get(
        f"{download_url.path}?{download_url.query}",
        headers={"X-Correlation-ID": "download-test"},
    )
    assert download.status_code == 200 and download.content.startswith(b"%PDF")
    assert api.get(f"/v1/exports/{export.json()['id']}/download").status_code == 401


def test_retrieval_reranks_expands_neighbors_and_deduplicates_blocks(tmp_path):
    api = client(tmp_path)
    raw = base64.b64encode(
        b"Context before the maintenance section.\n\n"
        b"The torque service fastener uses 10 Nm.\n\n"
        b"Context after the maintenance section.\n\n"
        b"The torque service fastener uses 10 Nm."
    ).decode()
    source = api.post(
        "/v1/sources/uploads",
        headers=headers(),
        json={
            "name": "Rerank guide",
            "filename": "rerank.txt",
            "content_base64": raw,
            "mime_type": "text/plain",
        },
    ).json()
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "Rerank project",
            "project_type": "brief",
            "brief": "Find torque guidance",
            "source_version_ids": [source["current_version_id"]],
        },
    ).json()
    evidence = api.get(
        f"/v1/projects/{project['id']}/sources/search",
        headers=headers(),
        params={"q": "torque service fastener", "limit": 4},
    )
    assert evidence.status_code == 200, evidence.text
    body = evidence.json()
    assert body["retrieval_version"] == "hybrid.v2"
    texts = [passage["text"] for passage in body["passages"]]
    assert len(texts) == len(set(texts))
    assert any("torque service fastener" in text.lower() for text in texts)
    assert any("context" in text.lower() for text in texts)


def test_validation_returns_deterministic_and_semantic_results(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Quality", "project_type": "brief", "brief": "Quality review"},
    ).json()
    response = api.post(f"/v1/projects/{project['id']}/validate", headers=headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["semantic"]["provider"] == "local-deterministic"
    assert body["summary"]["semantic"]["verdict"] == "needs_revision"
    assert any(finding["category"] == "semantic" for finding in body["findings"])


def test_patch_rejects_unknown_and_malformed_typed_content_blocks(tmp_path):
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Typed blocks", "project_type": "brief", "brief": "Typed content"},
    ).json()
    content = api.get(f"/v1/projects/{project['id']}/content", headers=headers()).json()
    response = api.post(
        f"/v1/projects/{project['id']}/patches",
        headers=headers(),
        json={
            "base_content_version_id": content["version"]["id"],
            "summary": "Malformed typed block",
            "operations": [
                {
                    "op": "insert_after",
                    "payload": {"block_type": "unknown_block", "text": "not allowed"},
                }
            ],
        },
    )
    assert response.status_code == 422
    codes = {finding["code"] for finding in response.json()["details"]["findings"]}
    assert "UNKNOWN_BLOCK_TYPE" in codes

    malformed = api.post(
        f"/v1/projects/{project['id']}/patches",
        headers=headers(),
        json={
            "base_content_version_id": content["version"]["id"],
            "summary": "Malformed table",
            "operations": [
                {
                    "op": "insert_after",
                    "payload": {"block_type": "table", "columns": ["A", "B"], "rows": [["only one"]]},
                }
            ],
        },
    )
    assert malformed.status_code == 422
    assert any(
        finding["code"] == "INVALID_BLOCK_PAYLOAD"
        for finding in malformed.json()["details"]["findings"]
    )
