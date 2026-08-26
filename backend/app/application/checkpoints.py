"""Application-owned projection of local execution checkpoints."""

from typing import Any

from ..ai.persistence.checkpoints import save_checkpoint
from ..config import Settings
from ..context import RuntimeContext
from ..models import AgentRun


def checkpoint_local_run(
    settings: Settings | None,
    ctx: RuntimeContext,
    run: AgentRun,
    phase: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist bounded execution state without making it product state."""

    if settings is None or settings.checkpoint_backend != "local":
        return
    save_checkpoint(
        settings,
        ctx.workspace_id,
        run.project_id,
        run.thread_id,
        {
            "schema_version": 1,
            "run_id": run.id,
            "project_id": run.project_id,
            "thread_id": run.thread_id,
            "phase": phase,
            "status": run.status,
            "cancel_requested": run.cancel_requested,
            "usage": run.usage_json,
            "budget": run.budget_json,
            "details": details or {},
        },
    )
