"""Content-free operational health and worker-liveness services."""

from typing import Any

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    AgentRun,
    DelegatedTask,
    DeletionRequest,
    ExportJob,
    IndexRebuildJob,
    IngestionJob,
    WorkerHeartbeat,
    as_aware_utc,
    utcnow,
)


def touch_worker_heartbeat(
    db: Session,
    worker_id: str,
    worker_type: str,
    workspace_id: str | None = None,
    *,
    status: str = "healthy",
    details: dict[str, Any] | None = None,
) -> WorkerHeartbeat:
    heartbeat = db.get(WorkerHeartbeat, worker_id)
    if not heartbeat:
        heartbeat = WorkerHeartbeat(
            worker_id=worker_id,
            worker_type=worker_type,
            workspace_id=workspace_id,
            status=status,
            details_json=details or {},
        )
        db.add(heartbeat)
    else:
        heartbeat.worker_type = worker_type
        heartbeat.workspace_id = workspace_id
        heartbeat.status = status
        heartbeat.details_json = details or heartbeat.details_json
    heartbeat.last_seen = utcnow()
    db.flush()
    return heartbeat


def operational_snapshot(db: Session, settings: Settings) -> dict[str, Any]:
    """Return bounded operational signals without exposing tenant content."""

    now = utcnow()
    heartbeat = db.query(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen.desc()).first()
    worker_status = "unknown"
    if heartbeat:
        age = (now - as_aware_utc(heartbeat.last_seen)).total_seconds()
        worker_status = "ok" if age <= settings.worker_heartbeat_timeout_seconds else "stale"
    queue_age: float | None = None
    for model in (
        AgentRun,
        IngestionJob,
        IndexRebuildJob,
        ExportJob,
        DelegatedTask,
        DeletionRequest,
    ):
        row = (
            db.query(model.created_at)
            .filter(model.status.in_(["queued", "pending"]))
            .order_by(model.created_at)
            .first()
        )
        if row and row[0]:
            age = max(0.0, (now - as_aware_utc(row[0])).total_seconds())
            queue_age = age if queue_age is None else max(queue_age, age)
    return {
        "checkpointer": "local" if settings.checkpoint_backend == "local" else "configured",
        "worker_heartbeat": worker_status,
        "oldest_queue_age_seconds": queue_age,
        "config_fingerprint": settings.effective_config_fingerprint(),
    }
