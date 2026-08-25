import base64

import httpx
import pytest
from app.config import Settings
from app.errors import GroundloomError
from app.main import create_app
from app.models import OutboxMessage, SourceBlock, SourceVersion
from app.ocr import HttpOCRProvider, LocalOCRProvider, build_ocr_provider
from fastapi.testclient import TestClient


def test_http_ocr_provider_is_bounded_and_validates_response(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"text": "Text extracted from the scanned document."}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    provider = HttpOCRProvider("https://ocr.example/v1", "secret-key")
    assert provider.extract(b"%PDF-1.7", "pdf").startswith("Text extracted")
    assert calls[0][0] == "https://ocr.example/v1/ocr"
    assert calls[0][1]["headers"] == {"Authorization": "Bearer secret-key"}
    assert base64.b64decode(calls[0][1]["json"]["content_base64"]) == b"%PDF-1.7"

    class BadResponse(Response):
        def json(self):
            return {"text": ""}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: BadResponse())
    with pytest.raises(GroundloomError) as malformed:
        provider.extract(b"pdf", "pdf")
    assert malformed.value.code == "PROVIDER_INVALID_RESPONSE"

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("ocr secret")),
    )
    with pytest.raises(GroundloomError) as outage:
        provider.extract(b"pdf", "pdf")
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True


def test_ocr_configuration_is_explicit_and_local_never_fabricates_text():
    with pytest.raises(GroundloomError) as local:
        LocalOCRProvider().extract(b"scanned", "pdf")
    assert local.value.code == "PROVIDER_MISCONFIGURED"
    with pytest.raises(GroundloomError) as missing:
        build_ocr_provider(Settings(ocr_provider="http"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"


def test_scanned_pdf_uses_ocr_stage_and_persists_immutable_text(monkeypatch, tmp_path):
    class FakeOCR:
        def extract(self, raw, extension):
            assert raw.startswith(b"%PDF-")
            assert extension == "pdf"
            return "OCR extracted maintenance guidance."

    monkeypatch.setattr("app.ocr.build_ocr_provider", lambda _settings: FakeOCR())
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ocr.db'}",
        object_store_path=tmp_path / "objects",
    )
    api = TestClient(create_app(settings))
    response = api.post(
        "/v1/sources/uploads",
        headers={"X-User-ID": "local-user", "X-Workspace-ID": "local-workspace"},
        json={
            "name": "Scanned guide",
            "filename": "scanned.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\nnot text-extractable\n%%EOF").decode(),
            "mime_type": "application/pdf",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["latest_status"] == "ready"
    with api.app.state.session_factory() as db:
        version = db.query(SourceVersion).one()
        assert version.status == "ready"
        assert db.query(SourceBlock).one().text == "OCR extracted maintenance guidance."
        stage_events = [
            row.payload["status"]
            for row in db.query(OutboxMessage).all()
            if row.event_type == "SourceStageChanged"
        ]
        assert "ocr" in stage_events
