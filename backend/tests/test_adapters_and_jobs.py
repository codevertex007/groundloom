import base64
import json
from pathlib import Path

import pytest
from app.ai.state.checkpoints import PostgresCheckpointProvider, build_checkpoint_provider
from app.auth import issue_context_token
from app.config import Settings
from app.context import RuntimeContext
from app.errors import GroundloomError
from app.main import create_app
from app.models import AgentRun, IngestionJob, SourceVersion
from app.object_store import LocalObjectStore, S3ObjectStore
from app.services import run_agent_worker_once, run_ingestion_worker_once
from app.telemetry import LangfuseTelemetry
from fastapi.testclient import TestClient
from scripts.backup_local import build_manifest, copy_tree, restore_backup, verify_manifest


def test_local_object_store_rejects_escape_and_round_trips(tmp_path: Path):
    store = LocalObjectStore(tmp_path / "objects")
    store.put_bytes("workspace/source.txt", b"evidence")
    assert store.get_bytes("workspace/source.txt") == b"evidence"
    assert store.exists("workspace/source.txt")
    with pytest.raises(GroundloomError):
        store.put_bytes("../outside.txt", b"blocked")


def test_external_adapters_classify_outages_without_leaking_provider_errors():
    class FakeClient:
        def __init__(self, code):
            self.code = code

        def get_object(self, **_kwargs):
            error = RuntimeError("provider secret should not escape")
            error.response = {"Error": {"Code": self.code}}
            raise error

    missing = object.__new__(S3ObjectStore)
    missing.bucket = "test"
    missing.client = FakeClient("NoSuchKey")
    with pytest.raises(GroundloomError) as missing_error:
        missing.get_bytes("missing.bin")
    assert missing_error.value.code == "RESOURCE_NOT_FOUND"
    outage = object.__new__(S3ObjectStore)
    outage.bucket = "test"
    outage.client = FakeClient("AccessDenied")
    with pytest.raises(GroundloomError) as outage_error:
        outage.get_bytes("artifact.bin")
    assert outage_error.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage_error.value.retryable is True

    class WriteFailingClient(FakeClient):
        def put_object(self, **_kwargs):
            error = RuntimeError("provider credentials should not escape")
            error.response = {"Error": {"Code": "AccessDenied"}}
            raise error

        def delete_object(self, **_kwargs):
            error = RuntimeError("provider credentials should not escape")
            error.response = {"Error": {"Code": "Timeout"}}
            raise error

    writes = object.__new__(S3ObjectStore)
    writes.bucket = "test"
    writes.client = WriteFailingClient("AccessDenied")
    writes.sse_mode = "none"
    writes.kms_key_id = None
    with pytest.raises(GroundloomError) as put_error:
        writes.put_bytes("artifact.bin", b"data")
    assert put_error.value.code == "DEPENDENCY_UNAVAILABLE"
    with pytest.raises(GroundloomError) as delete_error:
        writes.delete_bytes("artifact.bin")
    assert delete_error.value.retryable is True

    class FailingTelemetry:
        def create_event(self, **_kwargs):
            raise RuntimeError("telemetry credentials")

        def flush(self):
            raise RuntimeError("telemetry unavailable")

    telemetry = object.__new__(LangfuseTelemetry)
    telemetry.client = FailingTelemetry()
    telemetry.dropped_events = 0
    telemetry.last_error_class = None
    telemetry.emit("test", {"safe": True})
    telemetry.flush()
    assert telemetry.dropped_events == 2
    assert telemetry.last_error_class == "RuntimeError"


def test_s3_object_store_propagates_configured_server_side_encryption():
    calls = []

    class Client:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    aes = object.__new__(S3ObjectStore)
    aes.bucket = "groundloom"
    aes.client = Client()
    aes.sse_mode = "AES256"
    aes.kms_key_id = None
    aes.put_bytes("artifact.txt", b"safe")
    assert calls[-1]["ServerSideEncryption"] == "AES256"

    kms = object.__new__(S3ObjectStore)
    kms.bucket = "groundloom"
    kms.client = Client()
    kms.sse_mode = "aws:kms"
    kms.kms_key_id = "alias/groundloom"
    kms.put_bytes("artifact-kms.txt", b"safe")
    assert calls[-1]["ServerSideEncryption"] == "aws:kms"
    assert calls[-1]["SSEKMSKeyId"] == "alias/groundloom"


def test_production_requires_postgres_checkpoint_and_s3_storage():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
        migration_database_url="postgresql+psycopg://groundloom_migrator:password@localhost/groundloom",
        model_provider="openai",
        telemetry_provider="langfuse",
        object_store_backend="s3",
        object_store_bucket="groundloom",
        object_store_sse_mode="AES256",
        checkpoint_backend="postgres",
        auth_secret="local-test-secret-that-is-at-least-32-chars",
        auth_mode="hmac",
        public_base_url="https://groundloom.example",
        cors_origins=["https://app.groundloom.example"],
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_host="https://langfuse.example",
        agent_inline_local=False,
        source_scanner_provider="http",
        source_scanner_base_url="https://scanner.example",
        source_scanner_api_key="scanner-test-key",
        ocr_provider="http",
        ocr_base_url="https://ocr.example",
        ocr_api_key="ocr-test-key",
    )
    settings.validate_runtime()
    assert isinstance(build_checkpoint_provider(settings), PostgresCheckpointProvider)
    settings.object_store_sse_mode = "none"
    with pytest.raises(RuntimeError, match="server-side object-storage encryption"):
        settings.validate_runtime()


def test_production_rejects_weak_identity_and_local_domains():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
        migration_database_url="postgresql+psycopg://groundloom_migrator:password@localhost/groundloom",
        model_provider="openai",
        telemetry_provider="langfuse",
        object_store_backend="s3",
        object_store_bucket="groundloom",
        object_store_sse_mode="AES256",
        checkpoint_backend="postgres",
        auth_secret="too-short",
        auth_mode="hmac",
        public_base_url="http://localhost:8000",
        agent_inline_local=False,
    )
    with pytest.raises(RuntimeError, match="at least 32"):
        settings.validate_runtime()


def test_production_requires_distinct_worker_database_role():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
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
    )
    with pytest.raises(RuntimeError, match="groundloom_worker role"):
        settings.validate_runtime()


def test_production_requires_distinct_migration_database_role():
    settings = Settings(
        env="production",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
        migration_database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
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
    )
    with pytest.raises(RuntimeError, match="groundloom_migrator role"):
        settings.validate_runtime()


def test_postgres_staging_requires_runtime_role_split():
    settings = Settings(
        env="staging",
        database_url="postgresql+psycopg://groundloom_api:password@localhost/groundloom",
    )
    with pytest.raises(RuntimeError, match="separate worker database URL"):
        settings.validate_runtime()


def test_postgres_checkpoint_provider_uses_worker_connection():
    settings = Settings(
        checkpoint_backend="postgres",
        database_url="postgresql+psycopg://groundloom:password@localhost/groundloom",
        worker_database_url="postgresql+psycopg://groundloom_worker:password@localhost/groundloom",
    )
    provider = build_checkpoint_provider(settings)
    assert provider is not None
    assert provider.database_url == "postgresql://groundloom_worker:password@localhost/groundloom"


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


def test_local_restore_validates_before_overwriting_and_rejects_extra_objects(tmp_path: Path):
    database = tmp_path / "groundloom.db"
    objects = tmp_path / "objects"
    objects.mkdir()
    database.write_bytes(b"good database")
    (objects / "artifact.bin").write_bytes(b"good artifact")
    backup = tmp_path / "backup"
    backup.mkdir()
    backup_database = backup / "groundloom.db"
    backup_objects = backup / "objects"
    backup_database.write_bytes(database.read_bytes())
    copy_tree(objects, backup_objects)
    manifest = build_manifest(backup_database, backup_objects)
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    target_database = tmp_path / "target.db"
    target_objects = tmp_path / "target-objects"
    target_objects.mkdir()
    target_database.write_bytes(b"existing target")
    (target_objects / "existing.txt").write_bytes(b"preserve on failed restore")
    (backup_objects / "unexpected.bin").write_bytes(b"not in manifest")

    with pytest.raises(SystemExit, match="object inventory mismatch"):
        restore_backup(target_database, target_objects, backup)
    assert target_database.read_bytes() == b"existing target"
    assert (target_objects / "existing.txt").read_bytes() == b"preserve on failed restore"

    (backup_objects / "unexpected.bin").unlink()
    restore_backup(target_database, target_objects, backup)
    assert target_database.read_bytes() == b"good database"
    assert (target_objects / "artifact.bin").read_bytes() == b"good artifact"
    assert not (target_objects / "existing.txt").exists()


def test_agent_worker_claims_queued_runs_and_preserves_inline_local_mode(tmp_path: Path):
    settings = Settings(
        env="staging",
        auth_mode="hmac",
        auth_secret="staging-test-secret-that-is-long-enough",
        database_url=f"sqlite:///{tmp_path / 'agent-worker.db'}",
        object_store_path=tmp_path / "objects",
        agent_inline_local=False,
    )
    app = create_app(settings)
    token = issue_context_token("local-user", "local-workspace", settings.auth_secret)
    headers = {"Authorization": f"Bearer {token}"}
    api = TestClient(app)
    project = api.post(
        "/v1/projects",
        headers=headers,
        json={"name": "Queued agent", "project_type": "brief", "brief": "Worker-backed run"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    with app.state.session_factory() as db:
        result = run_agent_worker_once(db, settings, "agent-test-worker", limit=10)
        assert result == {"claimed": 1, "completed": 1, "requeued": 0, "failed": 0}
    message = api.post(
        f"/v1/projects/{project_id}/threads/messages",
        headers=headers,
        json={"text": "initialize"},
    )
    assert message.status_code == 202 and message.json()["status"] == "queued"
    with app.state.session_factory() as db:
        result = run_agent_worker_once(db, settings, "agent-test-worker", limit=10)
        assert result == {"claimed": 1, "completed": 1, "requeued": 0, "failed": 0}
        assert all(run.status == "completed" for run in db.query(AgentRun).all())
