"""Workspace-scoped audit recording and keyset-paginated reads."""

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..context import RuntimeContext
from ..errors import GroundloomError
from ..ids import new_id
from ..models import AuditEvent


def audit(
    db: Session,
    ctx: RuntimeContext,
    action: str,
    target_type: str,
    target_id: str | None,
    summary: str,
    result: str = "success",
) -> None:
    db.add(
        AuditEvent(
            id=new_id("aud"),
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            correlation_id=ctx.correlation_id,
            summary=summary[:2000],
        )
    )


def _audit_cursor(event: AuditEvent) -> str:
    created_at = event.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    payload = {"created_at": created_at.isoformat(), "id": event.id}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_audit_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        event_id = str(payload["id"])
        if not event_id:
            raise ValueError("missing event id")
        return created_at, event_id
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise GroundloomError("INVALID_CURSOR", "The audit cursor is invalid.", 400) from exc


def list_audit_events(
    db: Session, ctx: RuntimeContext, *, limit: int = 50, cursor: str | None = None
) -> dict[str, Any]:
    """Return a bounded workspace audit page and record the privileged read."""

    ctx.require("view audit events", {"workspace_admin", "organization_admin"})
    bounded_limit = max(1, min(limit, 100))
    query = (
        db.query(AuditEvent)
        .filter(AuditEvent.workspace_id == ctx.workspace_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    if cursor:
        created_at, event_id = _decode_audit_cursor(cursor)
        if db.get_bind().dialect.name == "sqlite":
            created_at = created_at.replace(tzinfo=None)
        query = query.filter(
            or_(
                AuditEvent.created_at < created_at,
                and_(AuditEvent.created_at == created_at, AuditEvent.id < event_id),
            )
        )
    rows = query.limit(bounded_limit + 1).all()
    page_rows = rows[:bounded_limit]
    result: list[dict[str, Any]] = []
    for event in page_rows:
        created_at = event.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        result.append(
            {
                "id": event.id,
                "actor_id": event.actor_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "result": event.result,
                "correlation_id": event.correlation_id,
                "summary": event.summary,
                "created_at": created_at,
            }
        )
    audit(db, ctx, "audit.read", "audit_event", None, f"Read {len(result)} bounded audit events")
    return {
        "items": result,
        "next_cursor": _audit_cursor(page_rows[-1]) if len(rows) > len(page_rows) else None,
    }
