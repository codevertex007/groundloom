import base64
from pathlib import Path

import pytest
from app.checkpoints import PostgresCheckpointProvider, build_checkpoint_provider
from app.config import Settings
from app.context import RuntimeContext
from app.errors import GroundloomError
from app.main import create_app
from app.models import IngestionJob, SourceVersion
from app.object_store import LocalObjectStore
from app.services import run_ingestion_worker_once
from fastapi.testclient import TestClient
from scripts.backup_local import build_manifest, copy_tree, verify_manifest


def test_local_object_store_rejects_escape_and_round_trips(tmp_path: Path):
    store = LocalObjectStore(tmp_path / "objects")
    store.put_bytes("workspace/source.txt", b"evidence")
    assert store.get_bytes("workspace/source.txt") == b"evidence"
    assert store.exists("workspace/source.txt")
    with pytest.raises(GroundloomError):
        store.put_bytes("../outside.txt", b"blocked")


def test_production_requires_postgres_checkpoint_and_s3_storage():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
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
    )
    settings.validate_runtime()
    assert isinstance(build_checkpoint_provider(settings), PostgresCheckpointProvider)


def test_production_rejects_weak_identity_and_local_domains():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        model_provider="openai",
        telemetry_provider="langfuse",
        object_store_backend="s3",
        object_store_bucket="groundloom",
        checkpoint_backend="postgres",
        auth_secret="too-short",
        auth_mode="hmac",
        public_base_url="http://localhost:8000",
    )
    with pytest.raises(RuntimeError, match="at least 32"):
        settings.validate_runtime()


def test_upload_creates_completed_ingestion_job(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    response = api.post(
        "/v1/sources/uploads",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
        json={
            "name": "Job source",
            "filename": "job.txt",
            "content_base64": base64.b64encode(b"Queued source content.").decode(),
        },
    )
    assert response.status_code == 201
    source_version_id = response.json()["current_version_id"]
    with app.state.session_factory() as db:
        version = db.get(SourceVersion, source_version_id)
        job = db.query(IngestionJob).filter_by(source_version_id=source_version_id).one()
        assert version.status == "ready"
        assert job.status == "completed"
        assert job.stage == "ready"


def test_ingestion_worker_reclaims_and_replays_a_queued_job(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    response = api.post(
        "/v1/sources/uploads",
        json={
            "name": "Worker source",
            "filename": "worker.txt",
            "mime_type": "text/plain",
            "content_base64": base64.b64encode(b"durable worker evidence").decode(),
        },
    )
    assert response.status_code == 201
    with app.state.session_factory() as db:
        job = db.query(IngestionJob).one()
        version = db.query(SourceVersion).one()
        job.status = "queued"
        job.stage = "queued"
        job.lease_owner = None
        job.lease_until = None
        version.status = "uploaded"
        db.commit()
        ctx = RuntimeContext(
            settings.local_user_id,
            settings.local_workspace_id,
            frozenset({"workspace_admin"}),
            "corr-worker-test",
        )
        result = run_ingestion_worker_once(db, ctx, settings, "worker-test")
        assert result == {"claimed": 1, "completed": 1, "failed": 0}
        assert db.query(IngestionJob).one().attempts == 1
        assert db.query(SourceVersion).one().status == "ready"


def test_parser_rejects_mime_spoofed_docx_and_persists_failure(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'parser.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    api = TestClient(app)
    response = api.post(
        "/v1/sources/uploads",
        json={
            "name": "Spoofed document",
            "filename": "spoof.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_base64": base64.b64encode(b"not a zip").decode(),
        },
    )
    assert response.status_code == 422
    with app.state.session_factory() as db:
        assert db.query(IngestionJob).one().status == "failed"
        assert db.query(SourceVersion).one().failure_code == "PARSE_FAILED"


def test_local_backup_manifest_verifies_database_and_objects(tmp_path: Path):
    database = tmp_path / "groundloom.db"
    objects = tmp_path / "objects"
    objects.mkdir()
    database.write_bytes(b"sqlite fixture")
    (objects / "workspace" ).mkdir()
    (objects / "workspace" / "artifact.bin").write_bytes(b"artifact")
    backup = tmp_path / "backup"
    backup.mkdir()
    backup_database = backup / "groundloom.db"
    backup_objects = backup / "objects"
    backup_database.write_bytes(database.read_bytes())
    copy_tree(objects, backup_objects)
    manifest = build_manifest(backup_database, backup_objects)
    restored = tmp_path / "restored"
    restored.mkdir()
    restored_database = restored / "groundloom.db"
    restored_objects = restored / "objects"
    restored_database.write_bytes(backup_database.read_bytes())
    copy_tree(backup_objects, restored_objects)
    verify_manifest(restored_database, restored_objects, manifest)
