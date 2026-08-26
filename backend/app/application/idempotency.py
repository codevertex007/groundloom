"""Workspace-scoped idempotency record handling."""

from sqlalchemy.orm import Session

from ..context import RuntimeContext
from ..errors import GroundloomError
from ..ids import new_id
from ..models import IdempotencyRecord


def remember_idempotency(
    db: Session, ctx: RuntimeContext, key: str | None, operation: str, response: dict
) -> dict:
    if not key:
        return response
    existing = db.query(IdempotencyRecord).filter_by(workspace_id=ctx.workspace_id, key=key).first()
    if existing:
        if existing.operation != operation:
            raise GroundloomError(
                "IDEMPOTENCY_CONFLICT",
                "The idempotency key was used for another operation.",
                409,
            )
        return existing.response_json
    db.add(
        IdempotencyRecord(
            id=new_id("idem"),
            workspace_id=ctx.workspace_id,
            key=key,
            operation=operation,
            response_json=response,
        )
    )
    return response
