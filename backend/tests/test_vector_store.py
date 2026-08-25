from pathlib import Path

import pytest
from app.config import Settings
from app.errors import GroundloomError
from app.main import create_app
from app.vector_store import LocalVectorIndexStore, PgVectorIndexStore, build_vector_index_store
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError


class _Dialect:
    name = "postgresql"


class _Bind:
    dialect = _Dialect()


class _RowsSession:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows or []
        self.error = error
        self.calls = []

    def get_bind(self):
        return _Bind()

    def execute(self, statement, params):
        self.calls.append((statement.text, params))
        if self.error:
            raise self.error
        return self.rows


def test_vector_backend_auto_selects_local_for_sqlite_and_pgvector_for_postgres(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'vector.db'}",
        object_store_path=tmp_path / "objects",
    )
    api = TestClient(create_app(settings))
    with api.app.state.session_factory() as db:
        assert isinstance(build_vector_index_store(db, settings), LocalVectorIndexStore)
    pg = build_vector_index_store(_RowsSession(), Settings(retrieval_index_backend="auto"))
    assert isinstance(pg, PgVectorIndexStore)


def test_pgvector_store_uses_scoped_upsert_and_bounded_semantic_search():
    rows = [("block-a", 0.91), ("block-a", 0.72), ("block-b", 0.44)]
    db = _RowsSession(rows=rows)
    store = PgVectorIndexStore()
    store.upsert(
        db,
        workspace_id="workspace-a",
        source_version_id="version-a",
        source_chunk_id="chunk-a",
        vector=[0.1, -0.2, 0.3],
    )
    scores = store.search(
        db,
        workspace_id="workspace-a",
        source_version_ids=["version-a"],
        vector=[0.1, -0.2, 0.3],
        limit=8,
    )
    assert scores == {"block-a": 0.91, "block-b": 0.44}
    insert_sql, insert_params = db.calls[0]
    assert "ON CONFLICT (source_chunk_id)" in insert_sql
    assert insert_params["workspace_id"] == "workspace-a"
    assert insert_params["embedding"] == "[0.1,-0.2,0.3]"
    search_sql, search_params = db.calls[1]
    assert "source_version_id IN" in search_sql
    assert search_params["source_version_ids"] == ["version-a"]
    assert search_params["limit"] == 8


def test_pgvector_provider_failures_are_typed_and_redacted():
    db = _RowsSession(error=SQLAlchemyError("database password should not escape"))
    with pytest.raises(GroundloomError) as error:
        PgVectorIndexStore().upsert(
            db,
            workspace_id="workspace-a",
            source_version_id="version-a",
            source_chunk_id="chunk-a",
            vector=[0.1, 0.2],
        )
    assert error.value.code == "DEPENDENCY_UNAVAILABLE"
    assert error.value.retryable is True
    assert "password" not in str(error.value)


def test_production_rejects_an_explicit_local_vector_index():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom_api:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
        migration_database_url="postgresql+psycopg://groundloom_migrator:password@localhost/groundloom",
        model_provider="openai",
        telemetry_provider="langfuse",
        object_store_backend="s3",
        object_store_bucket="groundloom",
        checkpoint_backend="postgres",
        auth_secret="local-test-secret-that-is-at-least-32-chars",
        auth_mode="hmac",
        public_base_url="https://groundloom.example",
        cors_origins=["https://app.groundloom.example"],
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_host="https://langfuse.example",
        agent_inline_local=False,
        retrieval_index_backend="local",
    )
    with pytest.raises(RuntimeError, match="pgvector retrieval index"):
        settings.validate_runtime()
