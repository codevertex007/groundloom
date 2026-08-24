"""Transactional-outbox delivery boundary.

Application writes create the outbox row in the same transaction as the
canonical mutation. A caller supplies the external delivery function; rows are
marked published only after that function succeeds.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import OutboxMessage

Delivery = Callable[[dict[str, Any]], None]


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
        deliver(message)
        row.published_at = datetime.now(UTC)
        published += 1
    db.commit()
    return published
