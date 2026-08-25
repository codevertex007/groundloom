from pathlib import Path

import httpx
import pytest
from app.config import Settings
from app.db import build_session_factory, init_database
from app.errors import GroundloomError
from app.ids import new_id
from app.models import OutboxMessage
from app.outbox import WebhookDelivery, build_delivery, publish_pending


def test_failed_outbox_delivery_persists_attempt_and_replays(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'outbox.db'}")
    init_database(settings.database_url)
    session = build_session_factory(settings.database_url)()
    row = OutboxMessage(
        id=new_id("evt"),
        workspace_id="local-workspace",
        event_type="TestEvent",
        aggregate_type="project",
        aggregate_id="project-1",
        payload={"safe": True},
    )
    session.add(row)
    session.commit()

    def unavailable(_message):
        raise GroundloomError("DEPENDENCY_UNAVAILABLE", "sink unavailable", 503, retryable=True)

    assert publish_pending(session, unavailable) == 0
    session.refresh(row)
    assert row.attempts == 1 and row.published_at is None
    delivered = []
    assert publish_pending(session, delivered.append) == 1
    session.refresh(row)
    assert row.attempts == 2 and row.published_at is not None
    assert delivered[0]["id"] == row.id
    session.close()


def test_webhook_delivery_redacts_outage_and_build_requires_explicit_configuration(monkeypatch):
    class Response:
        status_code = 503

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: Response())
    delivery = WebhookDelivery("https://events.example/groundloom", "secret-token")
    with pytest.raises(GroundloomError) as error:
        delivery({"id": "evt_1", "payload": {"safe": True}})
    assert error.value.code == "DEPENDENCY_UNAVAILABLE"
    assert "secret" not in error.value.message

    with pytest.raises(RuntimeError, match="delivery is disabled"):
        build_delivery(Settings())
