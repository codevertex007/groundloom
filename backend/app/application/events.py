"""Durable public-event and transactional-outbox recording."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..context import RuntimeContext
from ..ids import new_id
from ..models import AgentRun, OutboxMessage, PublicEvent


def outbox(
    db: Session,
    workspace_id: str | None,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict,
) -> None:
    db.add(
        OutboxMessage(
            id=new_id("out"),
            workspace_id=workspace_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
        )
    )


def append_event(
    db: Session, ctx: RuntimeContext, run: AgentRun, event_type: str, payload: dict
) -> PublicEvent:
    last = db.query(func.max(PublicEvent.seq)).filter_by(run_id=run.id).scalar() or 0
    pending = sum(1 for item in db.new if isinstance(item, PublicEvent) and item.run_id == run.id)
    event = PublicEvent(
        id=new_id("evt"),
        workspace_id=ctx.workspace_id,
        project_id=run.project_id,
        run_id=run.id,
        thread_id=run.thread_id,
        seq=last + pending + 1,
        schema_version=1,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    outbox(
        db,
        ctx.workspace_id,
        event_type,
        "agent_run",
        run.id,
        {"event_id": event.id, "seq": event.seq, **payload},
    )
    return event
