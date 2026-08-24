from dataclasses import dataclass, field

from fastapi import Header
from sqlalchemy.orm import Session

from .config import Settings
from .errors import GroundloomError
from .models import Membership


@dataclass(frozen=True)
class RuntimeContext:
    user_id: str
    workspace_id: str
    roles: frozenset[str]
    correlation_id: str
    project_id: str | None = None
    run_id: str | None = None
    budgets: dict[str, int] = field(default_factory=dict)

    def require(self, action: str, allowed: set[str]) -> None:
        if not self.roles.intersection(allowed):
            raise GroundloomError("PERMISSION_DENIED", f"You are not allowed to {action}.", 403)


def resolve_context(
    db: Session,
    settings: Settings,
    user_id: str | None,
    workspace_id: str | None,
    correlation_id: str | None,
) -> RuntimeContext:
    uid = user_id or settings.local_user_id
    wid = workspace_id or settings.local_workspace_id
    membership = db.query(Membership).filter_by(user_id=uid, workspace_id=wid, active=True).first()
    if not membership:
        raise GroundloomError("PERMISSION_DENIED", "The workspace is unavailable.", 403)
    return RuntimeContext(uid, wid, frozenset({membership.role}), correlation_id or "corr_local")


def context_dependency(
    db: Session,
    settings: Settings,
    x_user_id: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> RuntimeContext:
    return resolve_context(db, settings, x_user_id, x_workspace_id, x_correlation_id)
