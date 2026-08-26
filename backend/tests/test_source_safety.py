import base64
import io
import zipfile

import httpx
import pytest
from app.application.sources import run_ingestion_worker_once
from app.config import Settings
from app.context import RuntimeContext
from app.errors import GroundloomError
from app.ids import new_id
from app.main import create_app
from app.models import IngestionJob, Source, SourceVersion
from app.source_safety import HttpSourceScanner, LocalSourceScanner, build_source_scanner
from fastapi.testclient import TestClient

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def test_local_scanner_quarantines_standard_fixture_and_active_pdf():
    scanner = LocalSourceScanner()
    with pytest.raises(GroundloomError) as malware:
        scanner.scan(EICAR, "txt")
    assert malware.value.code == "SOURCE_QUARANTINED"
    with pytest.raises(GroundloomError) as active_pdf:
        scanner.scan(b"%PDF-1.7 /JavaScript", "pdf")
    assert active_pdf.value.code == "SOURCE_QUARANTINED"


def test_local_scanner_quarantines_macro_enabled_docx_features():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document />")
        archive.writestr("word/vbaProject.bin", b"macro")
    with pytest.raises(GroundloomError) as result:
        LocalSourceScanner().scan(buffer.getvalue(), "docx")
    assert result.value.code == "SOURCE_QUARANTINED"


def test_http_scanner_validates_verdict_and_redacts_provider_failures(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"verdict": "clean"}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    scanner = HttpSourceScanner("https://scanner.example/v1", "secret-key")
    scanner.scan(b"safe", "txt")
    assert calls[0][0] == "https://scanner.example/v1/scan"
    assert calls[0][1]["headers"] == {"Authorization": "Bearer secret-key"}
    assert base64.b64decode(calls[0][1]["json"]["content_base64"]) == b"safe"

    class QuarantineResponse(Response):
        def json(self):
            return {"verdict": "quarantine"}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: QuarantineResponse())
    with pytest.raises(GroundloomError) as quarantine:
        scanner.scan(b"unsafe", "txt")
    assert quarantine.value.code == "SOURCE_QUARANTINED"

    class BadResponse(Response):
        def json(self):
            return {"verdict": "unknown"}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: BadResponse())
    with pytest.raises(GroundloomError) as malformed:
        scanner.scan(b"safe", "txt")
    assert malformed.value.code == "PROVIDER_INVALID_RESPONSE"

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("scanner-secret")),
    )
    with pytest.raises(GroundloomError) as outage:
        scanner.scan(b"safe", "txt")
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True

    with pytest.raises(GroundloomError) as missing:
        build_source_scanner(Settings(source_scanner_provider="http"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"


def test_upload_quarantine_persists_terminal_state(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'quarantine.db'}",
        object_store_path=tmp_path / "objects",
    )
    api = TestClient(create_app(settings))
    response = api.post(
        "/v1/sources/uploads",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
        json={
            "name": "EICAR fixture",
            "filename": "fixture.txt",
            "content_base64": base64.b64encode(EICAR).decode(),
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SOURCE_QUARANTINED"
    with api.app.state.session_factory() as db:
        version = db.query(SourceVersion).one()
        assert version.status == "quarantined"
        assert version.failure_code == "SOURCE_QUARANTINED"
        assert db.query(IngestionJob).one().status == "failed"


def test_multipart_upload_enforces_streaming_size_bound(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'multipart-limit.db'}",
        object_store_path=tmp_path / "objects",
        max_upload_bytes=8,
    )
    api = TestClient(create_app(settings))
    response = api.post(
        "/v1/sources/uploads/multipart",
        params={"name": "Oversized multipart"},
        files={"file": ("too-large.txt", b"123456789", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_INPUT"


def test_ingestion_worker_preserves_quarantine_after_failure_replay(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'worker-quarantine.db'}",
        object_store_path=tmp_path / "objects",
    )
    app = create_app(settings)
    unsafe_pdf = b"%PDF-1.7 /JavaScript"
    object_key = "workspaces/local-workspace/sources/src-test/versions/1/original.pdf"
    app.state.object_store.put_bytes(object_key, unsafe_pdf)
    with app.state.session_factory() as db:
        source = Source(
            id=new_id("src"),
            workspace_id="local-workspace",
            name="Queued unsafe source",
            source_type="txt",
        )
        version = SourceVersion(
            id=new_id("sv"),
            workspace_id="local-workspace",
            source_id=source.id,
            version_no=1,
            status="uploaded",
            object_key=object_key,
            content_hash="fixture",
            mime_type="application/pdf",
            size_bytes=len(unsafe_pdf),
        )
        job = IngestionJob(
            id=new_id("ing"),
            workspace_id="local-workspace",
            source_version_id=version.id,
            status="queued",
            stage="queued",
        )
        db.add_all([source, version, job])
        db.commit()
        result = run_ingestion_worker_once(
            db,
            RuntimeContext("local-user", "local-workspace", frozenset({"author"}), "worker"),
            settings,
            "quarantine-worker",
        )
        assert result["failed"] == 1
        assert db.get(SourceVersion, version.id).status == "quarantined"
