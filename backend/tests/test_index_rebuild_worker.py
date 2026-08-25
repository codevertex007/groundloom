import base64
from pathlib import Path

from app.config import Settings
from app.context import RuntimeContext
from app.main import create_app
from app.models import IndexRebuildJob, SourceChunk
from app.services import run_index_rebuild_worker_once
from fastapi.testclient import TestClient


def test_index_rebuild_is_durable_idempotent_and_scoped(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'index.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    headers = {"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"}
    source = api.post(
        "/v1/sources/uploads",
        headers=headers,
        json={
            "name": "Rebuild source",
            "filename": "source.txt",
            "content_base64": base64.b64encode(b"Original evidence for rebuild.").decode(),
        },
    ).json()
    version_id = source["current_version_id"]
    first = api.post(f"/v1/source-versions/{version_id}/index-rebuilds", headers=headers)
    second = api.post(f"/v1/source-versions/{version_id}/index-rebuilds", headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    ctx = RuntimeContext("local-user", "local-workspace", frozenset({"workspace_admin"}), "index-test")
    with app.state.session_factory() as db:
        before = db.query(SourceChunk).filter_by(source_version_id=version_id).count()
        assert db.query(SourceChunk).filter_by(source_version_id=version_id).one().embedding_json
        result = run_index_rebuild_worker_once(db, ctx, "index-test-worker")
        after = db.query(SourceChunk).filter_by(source_version_id=version_id).count()
        assert before == after == 1
        assert db.query(SourceChunk).filter_by(source_version_id=version_id).one().embedding_json
        assert result == {"claimed": 1, "completed": 1, "failed": 0}
        assert db.query(IndexRebuildJob).one().status == "completed"
        replay = run_index_rebuild_worker_once(db, ctx, "index-test-worker")
        assert replay == {"claimed": 0, "completed": 0, "failed": 0}
