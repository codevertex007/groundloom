"""Transactional-outbox delivery boundary.

Application writes create the outbox row in the same transaction as the
canonical mutation. A caller supplies the external delivery function; rows are
marked published only after that function succeeds.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .config import Settings
from .errors import GroundloomError
from .models import OutboxMessage

Delivery = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class WebhookDelivery:
    """Narrow external outbox sink; consumers must deduplicate by event ID."""

    url: str
    token: str | None = None
    timeout_seconds: float = 10.0

    def __call__(self, message: dict[str, Any]) -> None:
        headers = {
            "Content-Type": "application/json",
            "X-Groundloom-Event-ID": str(message["id"]),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = httpx.post(
                self.url,
                headers=headers,
                json=message,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The outbox delivery service is temporarily unavailable.",
                503,
                retryable=True,
            ) from exc
        if response.status_code >= 500:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The outbox delivery service is temporarily unavailable.",
                503,
                retryable=True,
            )
        if not 200 <= response.status_code < 300:
            raise GroundloomError(
                "OUTBOX_REJECTED",
                "The outbox delivery service rejected the event.",
                502,
            )


def build_delivery(settings: Settings) -> Delivery:
    if settings.outbox_delivery_provider != "webhook":
        raise RuntimeError(
            "Outbox delivery is disabled; configure GROUNDLOOM_OUTBOX_DELIVERY_PROVIDER=webhook "
            "before starting outbox_worker.py"
        )
    if not settings.outbox_delivery_url:
        raise RuntimeError("Webhook outbox delivery requires GROUNDLOOM_OUTBOX_DELIVERY_URL")
    return WebhookDelivery(
        url=settings.outbox_delivery_url,
        token=settings.outbox_delivery_token,
        timeout_seconds=settings.outbox_delivery_timeout_seconds,
    )


def publish_pending(db: Session, deliver: Delivery, limit: int = 100) -> int:
    rows = (
        db.query(OutboxMessage)
        .filter(OutboxMessage.published_at.is_(None))
        .order_by(OutboxMessage.created_at)
        .limit(limit)
        .all()
    )
    published = 0
    for row in rows:
        row.attempts += 1
        message = {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "event_type": row.event_type,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": row.aggregate_id,
            "payload": row.payload,
        }
        try:
            deliver(message)
        except GroundloomError:
            # Persist the attempt so operators can distinguish a delivery
            # outage from an untouched event. The row remains replayable.
            db.commit()
            continue
        row.published_at = datetime.now(UTC)
        published += 1
        db.commit()
    return published
