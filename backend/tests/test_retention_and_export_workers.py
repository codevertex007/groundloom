import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from app.config import Settings
from app.context import RuntimeContext
from app.integrations.exports import render_content
from app.main import create_app
from app.models import DeletionRequest, ExportJob, Project, SourceVersion
from app.services import run_deletion_worker_once, run_export_worker_once
from fastapi.testclient import TestClient


def headers():
    return {"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"}


def test_staging_export_is_queued_and_worker_completes(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'exports.db'}",
        object_store_path=tmp_path / "objects",
        export_inline_local=False,
    )
    app = create_app(settings)
    api = TestClient(app)
    project = api.post(
        "/v1/projects", headers=headers(), json={"name": "Queued", "brief": "Export"}
    ).json()
    content = api.get(f"/v1/projects/{project['id']}/content", headers=headers()).json()
    response = api.post(
        "/v1/exports",
        headers=headers(),
        json={
            "project_id": project["id"],
            "content_version_id": content["version"]["id"],
            "format": "md",
        },
    )
    assert response.status_code == 202 and response.json()["status"] == "queued"
    ctx = RuntimeContext("local-user", "local-workspace", frozenset({"workspace_admin"}), "worker")
    with app.state.session_factory() as db:
        result = run_export_worker_once(db, ctx, settings, "test-export-worker")
        assert result == {"claimed": 1, "completed": 1, "failed": 0}
        assert db.query(ExportJob).one().status == "completed"


def test_project_deletion_is_scoped_audited_and_removes_artifacts(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'deletion.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    source = api.post(
        "/v1/sources/uploads",
        headers=headers(),
        json={
            "name": "Disposable",
            "filename": "evidence.txt",
            "content_base64": base64.b64encode(b"delete this evidence").decode(),
        },
    ).json()
    project = api.post(
        "/v1/projects",
        headers=headers(),
        json={"name": "Disposable project", "brief": "Delete me", "source_version_ids": [source["current_version_id"]]},
    ).json()
    deletion = api.post(
        f"/v1/projects/{project['id']}/deletion",
        headers=headers(),
        json={"idempotency_key": "delete-once"},
    )
    assert deletion.status_code == 202 and deletion.json()["status"] == "pending"
    ctx = RuntimeContext("local-user", "local-workspace", frozenset({"workspace_admin"}), "delete-worker")
    with app.state.session_factory() as db:
        result = run_deletion_worker_once(db, ctx, settings, "test-retention-worker")
        assert result["completed"] == 1
        assert db.query(DeletionRequest).one().status == "completed"
        assert db.query(Project).filter_by(id=project["id"]).first() is None
        assert db.query(SourceVersion).filter_by(id=source["current_version_id"]).first() is None
    assert not [item for item in (tmp_path / "objects").rglob("*") if item.is_file()]


def test_project_deletion_preserves_source_artifacts_shared_by_another_project(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'shared-deletion.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    source = api.post(
        "/v1/sources/uploads",
        headers=headers(),
        json={
            "name": "Shared evidence",
            "filename": "shared.txt",
            "content_base64": base64.b64encode(b"keep this shared evidence").decode(),
        },
    ).json()
    source_version_id = source["current_version_id"]
    first = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "First project",
            "brief": "Delete only this project",
            "source_version_ids": [source_version_id],
        },
    ).json()
    second = api.post(
        "/v1/projects",
        headers=headers(),
        json={
            "name": "Second project",
            "brief": "Keep the shared evidence",
            "source_version_ids": [source_version_id],
        },
    ).json()
    deletion = api.post(
        f"/v1/projects/{first['id']}/deletion",
        headers=headers(),
        json={"idempotency_key": "delete-first-only"},
    )
    assert deletion.status_code == 202
    ctx = RuntimeContext(
        "local-user", "local-workspace", frozenset({"workspace_admin"}), "shared-delete-worker"
    )
    with app.state.session_factory() as db:
        result = run_deletion_worker_once(db, ctx, settings, "test-shared-retention-worker")
        assert result["completed"] == 1
        assert db.query(Project).filter_by(id=first["id"]).first() is None
        assert db.query(Project).filter_by(id=second["id"]).first() is not None
        assert db.query(SourceVersion).filter_by(id=source_version_id).first() is not None
    assert list((tmp_path / "objects").rglob("*"))


def test_legal_hold_blocks_deletion_without_removing_project(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'hold.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    project = api.post(
        "/v1/projects", headers=headers(), json={"name": "Held", "brief": "Retain"}
    ).json()
    deletion = api.post(
        f"/v1/projects/{project['id']}/deletion", headers=headers(), json={}
    ).json()
    policy = api.put(
        "/v1/workspace/retention-policy",
        headers=headers(),
        json={"legal_hold": True, "sources_days": 365, "projects_days": 365, "agent_data_days": 90, "exports_days": 7, "audit_days": 2555},
    )
    assert policy.status_code == 200 and policy.json()["legal_hold"] is True
    with app.state.session_factory() as db:
        ctx = RuntimeContext("local-user", "local-workspace", frozenset({"workspace_admin"}), "hold-worker")
        result = run_deletion_worker_once(db, ctx, settings, "test-hold-worker")
        assert result["blocked"] == 1
        assert db.get(DeletionRequest, deletion["id"]).status == "blocked"
        assert db.query(Project).filter_by(id=project["id"], workspace_id="local-workspace").first() is not None


def test_exports_escape_untrusted_markup_in_html_and_docx(tmp_path: Path):
    blocks = [
        SimpleNamespace(
            block_type="paragraph",
            payload={"text": "<script>alert('xss')</script> & unsafe"},
        )
    ]
    html = render_content("<img src=x onerror=alert(1)>", blocks, "html").decode()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    docx = render_content("<title>", blocks, "docx")
    with ZipFile(BytesIO(docx)) as archive:
        document_xml = archive.read("word/document.xml")
    assert b"<script>" not in document_xml
    assert b"&lt;script&gt;" in document_xml
