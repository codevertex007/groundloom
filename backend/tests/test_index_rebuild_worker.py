import base64
from pathlib import Path

from app.application.sources import run_index_rebuild_worker_once
from app.config import Settings
from app.context import RuntimeContext
from app.main import create_app
from app.models import IndexRebuildJob, SourceChunk
from fastapi.testclient import TestClient


def test_index_rebuild_is_durable_idempotent_and_scoped(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'index.db'}",
        object_store_path=tmp_path / "objects",
        source_chunk_size=512,
        source_chunk_overlap=64,
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
            "content_base64": base64.b64encode(
                ("Original evidence for rebuild. " * 120).encode()
            ).decode(),
        },
    ).json()
    version_id = source["current_version_id"]
    first = api.post(f"/v1/source-versions/{version_id}/index-rebuilds", headers=headers)
    second = api.post(f"/v1/source-versions/{version_id}/index-rebuilds", headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    ctx = RuntimeContext("local-user", "local-workspace", frozenset({"workspace_admin"}), "index-test")
    with app.state.session_factory() as db:
        original = (
            db.query(SourceChunk)
            .filter_by(source_version_id=version_id)
            .order_by(SourceChunk.chunk_no)
            .all()
        )
        before = len(original)
        assert before > 1
        assert [chunk.chunk_no for chunk in original] == list(range(before))
        assert all(len(chunk.text) <= settings.source_chunk_size for chunk in original)
        assert all(chunk.embedding_json for chunk in original)
        original_texts = [chunk.text for chunk in original]
        result = run_index_rebuild_worker_once(db, ctx, "index-test-worker", settings=settings)
        rebuilt = (
            db.query(SourceChunk)
            .filter_by(source_version_id=version_id)
            .order_by(SourceChunk.chunk_no)
            .all()
        )
        assert before == len(rebuilt)
        assert [chunk.text for chunk in rebuilt] == original_texts
        assert all(chunk.embedding_json for chunk in rebuilt)
        assert result == {"claimed": 1, "completed": 1, "failed": 0}
        assert db.query(IndexRebuildJob).one().status == "completed"
        replay = run_index_rebuild_worker_once(db, ctx, "index-test-worker")
        assert replay == {"claimed": 0, "completed": 0, "failed": 0}
