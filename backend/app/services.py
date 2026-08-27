import base64
import hashlib
import logging
import re
import shutil
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .ai.agent import DEFAULT_MAX_TOOL_CALLS
from .ai.contracts import AgentConfigurationError
from .ai.evaluation.providers import RubricVersion, build_grader
from .ai.skill_author import SKILL_AUTHOR_PROMPT_VERSION, author_skill_package
from .application.audit import audit
from .application.checkpoints import checkpoint_local_run
from .application.events import append_event, outbox
from .application.idempotency import remember_idempotency
from .application.operations import touch_worker_heartbeat
from .config import Settings
from .content_types import validate_block_payload
from .context import RuntimeContext
from .db import set_tenant_context, set_worker_context
from .errors import GroundloomError
from .ids import new_id
from .integrations.ai.retrieval import search_evidence
from .integrations.exports import render_content
from .models import (
    AgentRun,
    AgentThread,
    ApprovalRequest,
    ContentBlock,
    ContentVersion,
    DelegatedTask,
    DeletionRequest,
    ExportJob,
    IdempotencyRecord,
    IngestionJob,
    Membership,
    MemoryItem,
    OutlineVersion,
    Patch,
    Project,
    ProjectConfigVersion,
    PublicEvent,
    RetentionPolicy,
    Skill,
    SkillVersion,
    Source,
    SourceBlock,
    SourceChunk,
    SourceVersion,
    Todo,
    User,
    ValidationFinding,
    ValidationRun,
    Workspace,
    WorkspacePreference,
    utcnow,
)
from .object_store import build_object_store
from .schemas import (
    DecisionIn,
    ExportCreate,
    MemoryWrite,
    PatchCreate,
    ProjectCreate,
    RetentionPolicyUpdate,
    SkillAuthorDraftCreate,
    SkillCreate,
    SkillDraftRepair,
    SkillForkCreate,
    WorkspacePreferencesUpdate,
)

logger = logging.getLogger(__name__)


def seed_local(db: Session, settings: Settings) -> None:
    set_tenant_context(db, settings.local_workspace_id)
    workspace = db.get(Workspace, settings.local_workspace_id)
    if not workspace:
        workspace = Workspace(id=settings.local_workspace_id, name=settings.local_workspace_name)
        db.add(workspace)
    user = db.get(User, settings.local_user_id)
    if not user:
        user = User(
            id=settings.local_user_id, email=settings.local_user_email, display_name="Local Author"
        )
        db.add(user)
    membership = (
        db.query(Membership)
        .filter_by(workspace_id=settings.local_workspace_id, user_id=settings.local_user_id)
        .first()
    )
    if not membership:
        db.add(
            Membership(
                id=new_id("mem"),
                workspace_id=settings.local_workspace_id,
                user_id=settings.local_user_id,
                role="workspace_admin",
                active=True,
            )
        )
    if not db.get(WorkspacePreference, settings.local_workspace_id):
        db.add(WorkspacePreference(workspace_id=settings.local_workspace_id))
    starter = db.query(Skill).filter_by(slug="source-grounded-writing", workspace_id=None).first()
    if not starter:
        starter = Skill(
            id=new_id("sk"),
            workspace_id=None,
            scope="starter",
            slug="source-grounded-writing",
            name="Source-grounded writing",
        )
        db.add(starter)
        db.flush()
        db.add(
            SkillVersion(
                id=new_id("skv"),
                workspace_id=None,
                skill_id=starter.id,
                version_no=1,
                status="published",
                description="Use evidence bundles, cite claims, and surface uncertainty.",
                package_json={
                    "content": "Use only authorized evidence. Cite factual claims and label gaps."
                },
                content_hash=hashlib.sha256(b"starter").hexdigest(),
                actor_id="system",
            )
        )
    db.commit()


def _project(db: Session, ctx: RuntimeContext, project_id: str) -> Project:
    project = db.query(Project).filter_by(id=project_id, workspace_id=ctx.workspace_id).first()
    if not project:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The project was not found.", 404)
    return project


def create_project(
    db: Session, ctx: RuntimeContext, body: ProjectCreate, settings: Settings | None = None
) -> Project:
    ctx.require("create projects", {"author", "reviewer", "workspace_admin", "organization_admin"})
    for version_id in body.source_version_ids:
        version = (
            db.query(SourceVersion)
            .filter_by(id=version_id, workspace_id=ctx.workspace_id, status="ready")
            .first()
        )
        if not version:
            raise GroundloomError(
                "SOURCE_NOT_READY",
                "Every selected source version must be ready and in this workspace.",
                422,
            )
    for version_id in body.skill_version_ids:
        skill_version = db.query(SkillVersion).filter_by(id=version_id, status="published").first()
        if not skill_version or (skill_version.workspace_id not in (None, ctx.workspace_id)):
            raise GroundloomError("PERMISSION_DENIED", "A selected skill is unavailable.", 403)
    preferences = ensure_workspace_preferences(db, ctx.workspace_id)
    effective_defaults = {
        "review_ai_edits": preferences.review_ai_edits,
        "require_citations": preferences.require_citations,
        "default_export": preferences.default_export,
        "require_plan_approval": preferences.require_plan_approval,
        "daily_token_budget": preferences.daily_token_budget,
        "daily_cost_budget_usd": preferences.daily_cost_budget_usd,
        **body.defaults,
    }
    project = Project(
        workspace_id=ctx.workspace_id,
        id=new_id("prj"),
        name=body.name,
        project_type=body.project_type,
        brief=body.brief,
    )
    db.add(project)
    db.flush()
    config = ProjectConfigVersion(
        id=new_id("cfg"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        version_no=1,
        source_version_ids=body.source_version_ids,
        skill_version_ids=body.skill_version_ids,
        defaults_json=effective_defaults,
        actor_id=ctx.user_id,
    )
    db.add(config)
    project.current_config_version_id = config.id
    content = ContentVersion(
        id=new_id("cv"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        version_no=1,
        status="accepted",
        provenance_json={"created_by": "system", "prompt_version": "groundloom.prompt.v1"},
    )
    db.add(content)
    project.current_content_version_id = content.id
    thread = AgentThread(
        id=new_id("thr"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        thread_key=f"project:{project.id}:primary",
        agent_definition_version="groundloom-project-agent.v1",
    )
    db.add(thread)
    db.flush()
    audit(
        db,
        ctx,
        "project.created",
        "project",
        project.id,
        "Created project and pinned initial configuration",
    )
    outbox(
        db,
        ctx.workspace_id,
        "ProjectCreated",
        "project",
        project.id,
        {"project_id": project.id, "config_version_id": config.id, "thread_id": thread.id},
    )
    db.commit()
    start_run(
        db,
        ctx,
        project,
        thread,
        "Project initialized; inspect the brief and selected evidence when ready.",
        "project-initialize",
        settings,
    )
    return project


def thread_for(db: Session, ctx: RuntimeContext, project_id: str) -> AgentThread:
    project = _project(db, ctx, project_id)
    thread = (
        db.query(AgentThread)
        .filter_by(project_id=project.id, workspace_id=ctx.workspace_id)
        .first()
    )
    if not thread:
        raise GroundloomError(
            "DEPENDENCY_UNAVAILABLE", "The project collaborator thread is unavailable.", 503
        )
    return thread


def _source_counts(db: Session, project: Project) -> tuple[int, int]:
    config = (
        db.get(ProjectConfigVersion, project.current_config_version_id)
        if project.current_config_version_id
        else None
    )
    source_ids = config.source_version_ids if config else []
    source_count = len(source_ids)
    section_count = (
        db.query(func.count(SourceBlock.id))
        .filter(SourceBlock.source_version_id.in_(source_ids))
        .scalar()
        if source_ids
        else 0
    )
    return source_count, int(section_count or 0)


def project_dto(db: Session, project: Project) -> dict[str, Any]:
    source_count, section_count = _source_counts(db, project)
    run = (
        db.query(AgentRun).filter_by(id=project.current_run_id).first()
        if project.current_run_id
        else None
    )
    return {
        "id": project.id,
        "name": project.name,
        "project_type": project.project_type,
        "brief": project.brief,
        "status": project.status,
        "current_config_version_id": project.current_config_version_id,
        "current_outline_version_id": project.current_outline_version_id,
        "current_content_version_id": project.current_content_version_id,
        "current_run_id": project.current_run_id,
        "source_count": source_count,
        "section_count": section_count,
        "latest_run_status": run.status if run else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _project_page_cursor(project: Project) -> str:
    updated_at = project.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    raw = f"{updated_at.timestamp():.6f}:{project.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_project_page_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        timestamp, project_id = raw.split(":", 1)
        return datetime.fromtimestamp(float(timestamp), UTC), project_id
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise GroundloomError("INVALID_CURSOR", "The project page cursor is invalid.", 400) from exc


def list_project_page(
    db: Session, ctx: RuntimeContext, *, limit: int = 50, cursor: str | None = None
) -> dict[str, Any]:
    """Return a bounded, workspace-scoped keyset page of project cards."""
    query = db.query(Project).filter_by(workspace_id=ctx.workspace_id)
    query = query.order_by(Project.updated_at.desc(), Project.id.desc())
    if cursor:
        timestamp, project_id = _decode_project_page_cursor(cursor)
        if db.get_bind().dialect.name == "sqlite":
            timestamp = timestamp.replace(tzinfo=None)
        query = query.filter(
            or_(
                Project.updated_at < timestamp,
                and_(Project.updated_at == timestamp, Project.id < project_id),
            )
        )
    rows = query.limit(max(1, min(limit, 100)) + 1).all()
    page_rows = rows[: max(1, min(limit, 100))]
    return {
        "items": [project_dto(db, project) for project in page_rows],
        "next_cursor": _project_page_cursor(page_rows[-1]) if len(rows) > len(page_rows) else None,
    }


def project_detail(db: Session, ctx: RuntimeContext, project_id: str) -> dict[str, Any]:
    project = _project(db, ctx, project_id)
    config = (
        db.get(ProjectConfigVersion, project.current_config_version_id)
        if project.current_config_version_id
        else None
    )
    thread = thread_for(db, ctx, project_id)
    todos = db.query(Todo).filter_by(project_id=project.id).order_by(Todo.sort_order).all()
    return {
        **project_dto(db, project),
        "config": {
            "id": config.id,
            "version_no": config.version_no,
            "source_version_ids": config.source_version_ids,
            "skill_version_ids": config.skill_version_ids,
            "defaults": config.defaults_json,
        }
        if config
        else {},
        "thread_id": thread.id,
        "todos": [
            {
                "id": t.id,
                "description": t.description,
                "status": t.status,
                "sort_order": t.sort_order,
                "run_id": t.run_id,
            }
            for t in todos
        ],
    }


def start_run(
    db: Session,
    ctx: RuntimeContext,
    project: Project,
    thread: AgentThread,
    request_text: str,
    idempotency_key: str,
    settings: Settings | None = None,
) -> AgentRun:
    existing = (
        db.query(AgentRun)
        .filter_by(
            workspace_id=ctx.workspace_id, project_id=project.id, idempotency_key=idempotency_key
        )
        .first()
    )
    if existing:
        return existing
    active_run = (
        db.query(AgentRun)
        .filter_by(workspace_id=ctx.workspace_id, project_id=project.id)
        .filter(
            AgentRun.status.in_(
                ["queued", "running", "waiting_for_user", "waiting_for_approval"]
            )
        )
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if active_run:
        raise GroundloomError(
            "INVALID_STATE",
            "Another project turn is active; wait, cancel, or resume it before sending a new message.",
            409,
        )
    config = (
        db.get(ProjectConfigVersion, project.current_config_version_id)
        if project.current_config_version_id
        else None
    )
    queue_for_worker = bool(
        settings
        and (
            (settings.env in {"staging", "production"} and settings.model_provider != "local")
            or not settings.agent_inline_local
        )
    )
    run = AgentRun(
        id=new_id("run"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        thread_id=thread.id,
        status="queued" if queue_for_worker else "running",
        request_text=request_text,
        idempotency_key=idempotency_key,
        pinned_config_json={
            "config_version_id": config.id if config else None,
            "source_version_ids": config.source_version_ids if config else [],
            "skill_version_ids": config.skill_version_ids if config else [],
            "prompt_version": "groundloom.prompt.v1",
            "tool_contract_version": "groundloom.tools.v1",
            "model_profile": (
                f"{settings.model_provider}:{settings.model_name}"
                if settings
                else "local.deterministic.v1"
            ),
            "retrieval_version": (
                "hybrid.pgvector.v2"
                if settings
                and (
                    settings.retrieval_index_backend == "pgvector"
                    or (
                        settings.retrieval_index_backend == "auto"
                        and settings.database_url.startswith("postgres")
                    )
                )
                else "hybrid.v2"
            ),
            "retrieval_config": {
                "index_backend": settings.retrieval_index_backend if settings else "local",
                "embedding_provider": settings.embedding_provider if settings else "local",
                "embedding_model": settings.embedding_model if settings else "deterministic-hash-v1",
                "embedding_dimensions": settings.embedding_dimensions if settings else 32,
                "reranker_provider": settings.reranker_provider if settings else "local",
                "reranker_model": settings.reranker_model if settings else "deterministic-overlap-v1",
            },
            "evaluator_version": "deterministic.v1",
            "actor_id": ctx.user_id,
            "correlation_id": ctx.correlation_id,
        },
        budget_json={
            "max_estimated_tokens": int((config.defaults_json if config else {}).get("max_estimated_tokens", 12000)),
            "max_tool_calls": int((config.defaults_json if config else {}).get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)),
            "max_cost_usd": float((config.defaults_json if config else {}).get("max_cost_usd", 1.0)),
        },
    )
    db.add(run)
    project.current_run_id = run.id
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        active_run = (
            db.query(AgentRun)
            .filter_by(workspace_id=ctx.workspace_id, project_id=project.id)
            .filter(
                AgentRun.status.in_(
                    ["queued", "running", "waiting_for_user", "waiting_for_approval"]
                )
            )
            .order_by(AgentRun.created_at.desc())
            .first()
        )
        if active_run:
            raise GroundloomError(
                "INVALID_STATE",
                "Another project turn is active; wait, cancel, or resume it before sending a new message.",
                409,
            ) from exc
        raise
    append_event(
        db,
        ctx,
        run,
        "run.started",
        {"status": run.status, "request": request_text[:500]},
    )
    db.commit()
    checkpoint_local_run(settings, ctx, run, "started")
    if not queue_for_worker:
        execute_agent_turn(db, ctx, run, settings)
    completed = db.get(AgentRun, run.id)
    if completed is None:
        raise GroundloomError("INTERNAL_ERROR", "The run disappeared before completion.", 500)
    return completed


def claim_agent_runs(
    db: Session, worker_id: str, *, limit: int = 10, lease_seconds: int = 300,
    max_attempts: int = 3,
) -> list[AgentRun]:
    now = utcnow()
    rows = (
        db.query(AgentRun)
        .filter(
            (AgentRun.status == "queued")
            | ((AgentRun.status == "running") & (AgentRun.lease_until < now))
        )
        .filter(AgentRun.attempts < max_attempts)
        .order_by(AgentRun.created_at)
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
        .all()
    )
    for run in rows:
        run.status = "running"
        run.attempts += 1
        run.lease_owner = worker_id
        run.lease_until = now + timedelta(seconds=lease_seconds)
    db.commit()
    return rows


def run_agent_worker_once(
    db: Session, settings: Settings, worker_id: str, *, limit: int = 10
) -> dict[str, int]:
    set_worker_context(db)
    touch_worker_heartbeat(db, worker_id, "agent", status="healthy", details={"limit": limit})
    db.commit()
    claimed = claim_agent_runs(
        db,
        worker_id,
        limit=limit,
        lease_seconds=300,
        max_attempts=max(1, settings.agent_max_attempts),
    )
    completed = failed = requeued = 0
    for run in claimed:
        actor_id = str(run.pinned_config_json.get("actor_id", settings.local_user_id))
        membership = (
            db.query(Membership)
            .filter_by(workspace_id=run.workspace_id, user_id=actor_id, active=True)
            .first()
        )
        if not membership:
            run.status = "failed"
            run.error_code = "WORKER_IDENTITY_UNAVAILABLE"
            run.lease_owner = None
            run.lease_until = None
            failed += 1
            db.commit()
            continue
        ctx = RuntimeContext(
            user_id=actor_id,
            workspace_id=run.workspace_id,
            roles=frozenset({membership.role}),
            correlation_id=str(run.pinned_config_json.get("correlation_id", f"worker:{worker_id}")),
        )
        try:
            execute_agent_turn(db, ctx, run, settings)
            refreshed = db.get(AgentRun, run.id)
            if refreshed and refreshed.status in {"completed", "waiting_for_approval", "waiting_for_user"}:
                completed += 1
            elif refreshed and refreshed.status == "failed":
                failed += 1
            else:
                requeued += 1
        except Exception:
            db.rollback()
            refreshed = db.get(AgentRun, run.id)
            if refreshed and refreshed.status not in {"failed", "completed", "cancelled"}:
                refreshed.status = "queued" if refreshed.attempts < settings.agent_max_attempts else "failed"
                refreshed.error_code = "AGENT_WORKER_FAILED"
                refreshed.lease_owner = None
                refreshed.lease_until = None
                if refreshed.status == "queued":
                    requeued += 1
                else:
                    failed += 1
                db.commit()
            else:
                failed += 1
    result = {
        "claimed": len(claimed),
        "completed": completed,
        "requeued": requeued,
        "failed": failed,
    }
    touch_worker_heartbeat(db, worker_id, "agent", status="healthy", details=result)
    db.commit()
    return result


def approval_dto(approval: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": approval.id,
        "project_id": approval.project_id,
        "thread_id": approval.thread_id,
        "run_id": approval.run_id,
        "kind": approval.kind,
        "status": approval.status,
        "payload": approval.payload_json,
        "decision_reason": approval.decision_reason,
        "decided_by": approval.decided_by,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
    }


def list_run_approvals(db: Session, ctx: RuntimeContext, run_id: str) -> list[dict[str, Any]]:
    ctx.require(
        "view run approvals",
        {"viewer", "author", "reviewer", "workspace_admin", "organization_admin"},
    )
    return [
        approval_dto(item)
        for item in db.query(ApprovalRequest)
        .filter_by(run_id=run_id, workspace_id=ctx.workspace_id)
        .order_by(ApprovalRequest.created_at)
        .all()
    ]


def resolve_approval(
    db: Session,
    ctx: RuntimeContext,
    approval_id: str,
    decision: str,
    reason: str | None,
    settings: Settings,
) -> dict[str, Any]:
    ctx.require("resolve approval", {"author", "reviewer", "workspace_admin", "organization_admin"})
    approval = (
        db.query(ApprovalRequest)
        .filter_by(id=approval_id, workspace_id=ctx.workspace_id)
        .first()
    )
    if not approval:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The approval request was not found.", 404)
    if approval.status != "pending":
        return approval_dto(approval)
    run = db.query(AgentRun).filter_by(id=approval.run_id, workspace_id=ctx.workspace_id).first()
    if not run:
        raise GroundloomError("DEPENDENCY_UNAVAILABLE", "The approval run is unavailable.", 503)
    approval.status = decision
    approval.decision_reason = reason
    approval.decided_by = ctx.user_id
    approval.decided_at = utcnow()
    append_event(
        db,
        ctx,
        run,
        "approval.resolved",
        {"approval_id": approval.id, "kind": approval.kind, "status": decision},
    )
    audit(
        db,
        ctx,
        "approval.resolved",
        "approval_request",
        approval.id,
        f"{decision.title()} {approval.kind} approval",
    )
    if decision == "approved":
        run.pinned_config_json = {
            **run.pinned_config_json,
            "approved_outline_id": approval.payload_json.get("outline_version_id"),
        }
        queue_for_worker = bool(
            (
                settings.env in {"staging", "production"}
                and settings.model_provider != "local"
            )
            or not settings.agent_inline_local
        )
        run.status = "queued" if queue_for_worker else "running"
        db.commit()
        if not queue_for_worker:
            execute_agent_turn(db, ctx, run, settings)
    else:
        run.status = "cancelled"
        run.error_code = "PLAN_REJECTED"
        append_event(
            db,
            ctx,
            run,
            "run.cancelled",
            {"status": "cancelled", "reason": "The proposed plan was rejected."},
        )
        db.commit()
    return approval_dto(approval)


def enforce_run_budget(db: Session, ctx: RuntimeContext, run: AgentRun) -> bool:
    """Stop optional agent work before a configured per-run/workspace budget is exceeded."""
    usage = run.usage_json or {}
    estimated_tokens = int(usage.get("estimated_input_tokens", 0)) + int(
        usage.get("output_tokens", 0)
    )
    tool_calls = int(usage.get("tool_calls", 0))
    estimated_cost = float(usage.get("estimated_cost_usd", 0.0))
    per_run_tokens = int((run.budget_json or {}).get("max_estimated_tokens", 12_000))
    per_run_tools = int((run.budget_json or {}).get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS))
    per_run_cost = float((run.budget_json or {}).get("max_cost_usd", 1.0))
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    workspace_runs = (
        db.query(AgentRun)
        .filter(AgentRun.workspace_id == ctx.workspace_id, AgentRun.created_at >= day_start)
        .all()
    )
    workspace_tokens = 0
    workspace_cost = 0.0
    for other in workspace_runs:
        if other.id == run.id:
            continue
        other_usage = other.usage_json or {}
        workspace_tokens += int(other_usage.get("estimated_input_tokens", 0)) + int(
            other_usage.get("output_tokens", 0)
        )
        workspace_cost += float(other_usage.get("estimated_cost_usd", 0.0))
    preferences = ensure_workspace_preferences(db, ctx.workspace_id)
    stop_reason: str | None = None
    if estimated_tokens > per_run_tokens:
        stop_reason = "The request exceeds the per-run token budget."
    elif tool_calls > per_run_tools:
        stop_reason = "The request exceeds the per-run tool budget."
    elif estimated_cost > per_run_cost:
        stop_reason = "The request exceeds the per-run cost budget."
    elif workspace_tokens + estimated_tokens > preferences.daily_token_budget:
        stop_reason = "The workspace daily token budget has been reached."
    elif workspace_cost + estimated_cost > preferences.daily_cost_budget_usd:
        stop_reason = "The workspace daily cost budget has been reached."
    if stop_reason is None:
        return False
    run.status = "waiting_for_user"
    run.error_code = "BUDGET_EXCEEDED"
    add_todo(db, ctx, run, "Review or increase the active budget before continuing", "waiting_for_user", 99)
    append_event(
        db,
        ctx,
        run,
        "budget.stopped",
        {
            "status": "waiting_for_user",
            "estimated_tokens": estimated_tokens,
            "tool_calls": tool_calls,
            "reason": stop_reason,
        },
    )
    append_event(
        db,
        ctx,
        run,
        "run.waiting",
        {"status": "waiting_for_user", "reason": "Budget approval or adjustment is required."},
    )
    audit(db, ctx, "run.budget_stopped", "agent_run", run.id, "Stopped optional agent work at a budget boundary")
    db.commit()
    return True


def execute_deep_agent_turn(
    db: Session, ctx: RuntimeContext, run: AgentRun, settings: Settings
) -> None:
    run.usage_json = {
        "estimated_input_tokens": max(1, len(run.request_text) // 4),
        "output_tokens": 0,
        "tool_calls": 0,
        "estimated_cost_usd": 0.0,
    }
    checkpoint_local_run(settings, ctx, run, "executing", {"provider": settings.model_provider})
    if enforce_run_budget(db, ctx, run):
        checkpoint_local_run(settings, ctx, run, "waiting_for_budget")
        return
    from .ai.runtime.factory import build_agent_runtime

    thread = db.query(AgentThread).filter_by(id=run.thread_id, workspace_id=ctx.workspace_id).first()
    if not thread:
        raise GroundloomError("DEPENDENCY_UNAVAILABLE", "The project thread is unavailable.", 503)
    result: dict[str, Any] | None = None
    provider_error: Exception | None = None

    def provider_progress(event_type: str, payload: dict[str, Any]) -> None:
        """Persist provider stream metadata before it is exposed over SSE."""
        append_event(db, ctx, run, event_type, payload)
        db.commit()

    def provider_cancel_requested() -> bool:
        # Read the flag through a scalar query so a worker can observe a
        # cancellation committed by the API while the provider is streaming.
        value = db.query(AgentRun.cancel_requested).filter(AgentRun.id == run.id).scalar()
        return bool(value)

    attempts = max(1, min(settings.agent_max_attempts, 5))
    for attempt in range(attempts):
        if run.cancel_requested:
            run.status = "cancelled"
            append_event(db, ctx, run, "run.cancelled", {"status": "cancelled"})
            db.commit()
            checkpoint_local_run(settings, ctx, run, "cancelled")
            return
        try:
            runtime = build_agent_runtime(settings.model_provider, settings)
            result = runtime.invoke(
                db,
                ctx,
                run.project_id,
                thread.thread_key,
                run.request_text,
                progress_callback=provider_progress,
                cancel_check=provider_cancel_requested,
                max_tool_calls=int((run.budget_json or {}).get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)),
            )
            provider_error = None
            break
        except AgentConfigurationError as exc:
            # Fixed configuration cannot self-heal between attempts; retrying
            # would only repeat the same failure while burning latency/cost.
            provider_error = exc
            logger.error("Agent run %s cannot start: %s", run.id, exc)
            break
        except Exception as exc:
            provider_error = exc
            logger.exception("Agent run %s failed on attempt %d/%d", run.id, attempt + 1, attempts)
            if attempt + 1 < attempts:
                time.sleep(min(settings.agent_retry_backoff_seconds * (2**attempt), 2.0))
    if provider_error is not None or result is None:
        failure = provider_error or RuntimeError("agent provider returned no result")
        misconfigured = isinstance(failure, AgentConfigurationError)
        retryable = not misconfigured
        run.status = "failed"
        run.error_code = "AGENT_MISCONFIGURED" if misconfigured else "AGENT_PROVIDER_ERROR"
        append_event(
            db,
            ctx,
            run,
            "run.failed",
            {"status": "failed", "error_code": run.error_code, "retryable": retryable},
        )
        audit(
            db,
            ctx,
            "run.failed",
            "agent_run",
            run.id,
            f"Deep Agents provider execution failed: {failure}" if misconfigured else "Deep Agents provider execution failed",
            "failure",
        )
        db.commit()
        checkpoint_local_run(settings, ctx, run, "failed", {"error_code": run.error_code})
        raise GroundloomError(
            "AGENT_MISCONFIGURED" if misconfigured else "DEPENDENCY_UNAVAILABLE",
            str(failure) if misconfigured else "The configured agent provider could not complete the run.",
            503,
            retryable=retryable,
        ) from failure
    if result.get("cancelled") or provider_cancel_requested():
        run.status = "cancelled"
        append_event(db, ctx, run, "run.cancelled", {"status": "cancelled"})
        audit(db, ctx, "run.cancelled", "agent_run", run.id, "Cancelled Deep Agents project turn")
        db.commit()
        checkpoint_local_run(settings, ctx, run, "cancelled")
        return
    messages = result.get("messages", []) if isinstance(result, dict) else []
    last = messages[-1] if messages else {}
    content = last.get("content", "") if isinstance(last, dict) else getattr(last, "content", "")
    if isinstance(content, list):
        content = " ".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    raw_usage = result.get("usage", {}) if isinstance(result, dict) else {}
    run.usage_json = {
        "input_tokens": int(raw_usage.get("input_tokens", max(1, len(run.request_text) // 4))),
        "output_tokens": int(raw_usage.get("output_tokens", max(1, len(str(content)) // 4))),
        "tool_calls": int(raw_usage.get("tool_calls", 0)),
        "estimated_cost_usd": float(raw_usage.get("estimated_cost_usd", 0.0)),
    }
    append_event(
        db,
        ctx,
        run,
        "assistant.message",
        {"text": str(content)[:4000], "provider": settings.model_provider},
    )
    run.status = "completed"
    append_event(
        db,
        ctx,
        run,
        "run.completed",
        {"status": "completed", "summary": "Deep Agents collaborator completed the turn."},
    )
    audit(db, ctx, "run.completed", "agent_run", run.id, "Completed Deep Agents project turn")
    db.commit()
    checkpoint_local_run(settings, ctx, run, "completed", {"provider": settings.model_provider})


def execute_agent_turn(
    db: Session, ctx: RuntimeContext, run: AgentRun, settings: Settings | None = None
) -> None:
    """Dispatch one agent turn to the configured runtime.

    When ``model_provider == "local"`` (the default, and what the test/e2e
    suite runs under), everything below this branch is a deterministic,
    keyword-matched state machine — it never constructs a DeepAgents graph
    and does not exercise the real middleware/subagent/tool-selection
    behavior in ``execute_deep_agent_turn``. It is a fast, credential-free
    double for the product's API/persistence/event contract, not a fidelity
    double for the agent's reasoning: tests that only exercise this path
    prove the surrounding product surface works, not that the LLM-driven
    harness does. Real agent behavior needs a live provider and
    ``execute_deep_agent_turn`` — see ``backend/tests/test_optional_provider_contracts.py``
    for the tests that drive an actual compiled graph.
    """
    if settings and settings.model_provider != "local":
        execute_deep_agent_turn(db, ctx, run, settings)
        return
    if run.pinned_config_json.get("approved_outline_id"):
        _complete_approved_plan(db, ctx, run, settings)
        return
    project = _project(db, ctx, run.project_id)
    text = run.request_text.lower()
    run.usage_json = {
        "input_chars": len(run.request_text),
        "estimated_input_tokens": max(1, len(run.request_text) // 4),
        "output_tokens": 0,
        "tool_calls": 0,
        "estimated_cost_usd": 0.0,
    }
    is_initialization = (
        "initialize" in text or "initialized" in text or "hello" in text
    )
    checkpoint_local_run(settings, ctx, run, "executing")
    if not is_initialization and enforce_run_budget(db, ctx, run):
        checkpoint_local_run(settings, ctx, run, "waiting_for_budget")
        return
    if run.cancel_requested:
        run.status = "cancelled"
        append_event(db, ctx, run, "run.cancelled", {"status": "cancelled"})
        db.commit()
        checkpoint_local_run(settings, ctx, run, "cancelled")
        return
    if is_initialization:
        add_todo(
            db, ctx, run, "Review the project brief and selected source manifest", "completed", 0
        )
        append_event(
            db,
            ctx,
            run,
            "run.completed",
            {"status": "completed", "summary": "Project collaborator is ready."},
        )
        run.status = "completed"
        run.usage_json = {**run.usage_json, "output_tokens": 8, "estimated_cost_usd": 0.00001}
        audit(db, ctx, "run.completed", "agent_run", run.id, "Initialized primary project thread")
        db.commit()
        checkpoint_local_run(settings, ctx, run, "completed", {"initialization": True})
        return
    add_todo(db, ctx, run, "Understand the request and inspect project state", "completed", 0)
    evidence = search_evidence(
        db, ctx, project.id, run.request_text, limit=8, settings=settings
    )
    passage_dicts = [passage.model_dump() for passage in evidence.passages]
    append_event(
        db,
        ctx,
        run,
        "tool.completed",
        {
            "tool_id": "TOOL-RET-001",
            "name": "search_source_passages",
            "passage_count": len(evidence.passages),
            "gaps": evidence.gaps,
        },
    )
    run.usage_json = {**run.usage_json, "tool_calls": 1}
    if enforce_run_budget(db, ctx, run):
        checkpoint_local_run(settings, ctx, run, "waiting_for_budget", {"tool": "search_source_passages"})
        return
    wants_draft = any(word in text for word in ("draft", "generate", "outline", "write", "create"))
    if not wants_draft:
        add_todo(db, ctx, run, "Answer the grounded project question", "completed", 1)
        answer = (
            evidence.passages[0].text
            if evidence.passages
            else "I could not find authorized evidence for that request. Select a ready source version or ask for a project-level next step."
        )
        append_event(
            db,
            ctx,
            run,
            "artifact.delta",
            {"text": answer[:2000], "citations": [p["passage_id"] for p in passage_dicts[:3]]},
        )
        append_event(
            db,
            ctx,
            run,
            "run.completed",
            {"status": "completed", "summary": "Grounded response produced."},
        )
        run.status = "completed"
        run.usage_json = {**run.usage_json, "output_tokens": max(1, len(answer) // 4), "estimated_cost_usd": 0.00002}
        db.commit()
        checkpoint_local_run(settings, ctx, run, "completed", {"response": "grounded_answer"})
        return
    add_todo(db, ctx, run, "Propose a reviewable outline", "in_progress", 1)
    outline_items = [
        {
            "id": new_id("mod"),
            "title": "Context and objective",
            "description": "Frame the brief and intended outcome.",
            "status": "proposed",
        },
        {
            "id": new_id("mod"),
            "title": "Evidence and key findings",
            "description": "Synthesize authorized source passages.",
            "status": "proposed",
        },
        {
            "id": new_id("mod"),
            "title": "Recommendations and next steps",
            "description": "Turn supported findings into actionable guidance.",
            "status": "proposed",
        },
    ]
    config = db.get(ProjectConfigVersion, project.current_config_version_id)
    next_outline = (
        db.query(func.max(OutlineVersion.version_no)).filter_by(project_id=project.id).scalar() or 0
    ) + 1
    outline = OutlineVersion(
        id=new_id("ov"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        version_no=next_outline,
        status="proposed",
        outline_json=outline_items,
        provenance_json={
            "run_id": run.id,
            "evidence_passage_ids": [p["passage_id"] for p in passage_dicts],
            "pinned_config": run.pinned_config_json,
            "skill_version_ids": config.skill_version_ids if config else [],
        },
    )
    db.add(outline)
    db.flush()
    project.current_outline_version_id = outline.id
    for item in outline_items:
        task = DelegatedTask(
            id=new_id("task"),
            workspace_id=ctx.workspace_id,
            project_id=project.id,
            parent_run_id=run.id,
            task_type="module_writer",
            status="completed",
            objective=item["description"],
            input_refs={
                "outline_item_id": item["id"],
                "evidence_passage_ids": [p["passage_id"] for p in passage_dicts],
            },
            result_refs={"status": "proposal_reconciled"},
        )
        db.add(task)
        append_event(
            db,
            ctx,
            run,
            "subagent.completed",
            {
                "task_id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "objective": task.objective,
            },
        )
    configured_approval = (
        config.defaults_json.get("require_plan_approval")
        if config and "require_plan_approval" in config.defaults_json
        else ensure_workspace_preferences(db, ctx.workspace_id).require_plan_approval
    )
    requires_approval = bool(configured_approval) or (
        "approve the plan" in text or "plan approval" in text
    )
    if requires_approval:
        approval = ApprovalRequest(
            id=new_id("approval"),
            workspace_id=ctx.workspace_id,
            project_id=project.id,
            thread_id=run.thread_id,
            run_id=run.id,
            kind="plan",
            status="pending",
            payload_json={"outline_version_id": outline.id, "items": outline_items},
        )
        db.add(approval)
        run.status = "waiting_for_approval"
        add_todo(db, ctx, run, "Approve or reject the proposed outline", "waiting_for_user", 2)
        append_event(
            db,
            ctx,
            run,
            "approval.required",
            {"approval_id": approval.id, "kind": approval.kind, "outline_version_id": outline.id},
        )
        append_event(
            db,
            ctx,
            run,
            "run.waiting",
            {"status": "waiting_for_approval", "reason": "Plan approval is required."},
        )
        audit(db, ctx, "approval.required", "approval_request", approval.id, "Plan approval requested")
        db.commit()
        checkpoint_local_run(settings, ctx, run, "waiting_for_approval", {"approval_id": approval.id})
        return
    append_event(
        db, ctx, run, "plan.proposed", {"outline_version_id": outline.id, "items": outline_items}
    )
    add_todo(db, ctx, run, "Propose cited content changes for review", "in_progress", 2)
    current = db.get(ContentVersion, project.current_content_version_id)
    if current is None:
        raise GroundloomError(
            "DEPENDENCY_UNAVAILABLE", "The project has no current content version.", 503
        )
    operations = [
        {
            "op": "insert_after",
            "after_block_id": None,
            "payload": {"block_type": "heading", "text": project.name},
        },
        {
            "op": "insert_after",
            "after_block_id": None,
            "payload": {
                "block_type": "paragraph",
                "text": f"{project.brief}\n\nThis draft is grounded in {len(passage_dicts)} authorized source passage(s).",
                "citations": [p["passage_id"] for p in passage_dicts[:3]],
            },
        },
    ]
    patch = Patch(
        id=new_id("pat"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        base_content_version_id=current.id,
        status="presented",
        operations=operations,
        summary="Initial source-grounded draft proposal",
        validation_json={"status": "valid", "findings": []},
        actor_id=ctx.user_id,
    )
    db.add(patch)
    db.flush()
    append_event(
        db,
        ctx,
        run,
        "patch.proposed",
        {
            "patch_id": patch.id,
            "base_content_version_id": current.id,
            "operation_count": len(operations),
            "summary": patch.summary,
        },
    )
    add_todo(db, ctx, run, "Validate citations and present the proposal", "completed", 3)
    append_event(
        db,
        ctx,
        run,
        "validation.completed",
        {"status": "passed", "finding_count": 0, "patch_id": patch.id},
    )
    append_event(
        db,
        ctx,
        run,
        "run.completed",
        {
            "status": "completed",
            "summary": "Outline and cited draft proposal are ready for review.",
            "patch_id": patch.id,
            "outline_version_id": outline.id,
        },
    )
    run.status = "completed"
    run.usage_json = {
        **run.usage_json,
        "output_tokens": max(1, len(project.brief) // 4),
        "tool_calls": 1,
        "estimated_cost_usd": 0.00005,
    }
    audit(
        db,
        ctx,
        "run.completed",
        "agent_run",
        run.id,
        "Produced adaptive outline and content proposal",
    )
    db.commit()
    checkpoint_local_run(settings, ctx, run, "completed", {"patch_id": patch.id, "outline_version_id": outline.id})


def _complete_approved_plan(
    db: Session, ctx: RuntimeContext, run: AgentRun, settings: Settings | None = None
) -> None:
    """Continue the same local primary-agent run after a plan approval interrupt."""
    project = _project(db, ctx, run.project_id)
    evidence = search_evidence(
        db, ctx, project.id, run.request_text, limit=8, settings=settings
    )
    passage_dicts = [passage.model_dump() for passage in evidence.passages]
    current = db.get(ContentVersion, project.current_content_version_id)
    if current is None:
        raise GroundloomError("DEPENDENCY_UNAVAILABLE", "The project has no current content version.", 503)
    patch = Patch(
        id=new_id("pat"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        base_content_version_id=current.id,
        status="presented",
        operations=[
            {"op": "insert_after", "after_block_id": None, "payload": {"block_type": "heading", "text": project.name}},
            {
                "op": "insert_after",
                "after_block_id": None,
                "payload": {
                    "block_type": "paragraph",
                    "text": f"{project.brief}\n\nThis draft is grounded in {len(passage_dicts)} authorized source passage(s).",
                    "citations": [p["passage_id"] for p in passage_dicts[:3]],
                },
            },
        ],
        summary="Approved source-grounded draft proposal",
        validation_json={"status": "valid", "findings": []},
        actor_id=ctx.user_id,
    )
    db.add(patch)
    db.flush()
    add_todo(db, ctx, run, "Propose cited content changes for review", "completed", 2)
    append_event(db, ctx, run, "patch.proposed", {"patch_id": patch.id, "base_content_version_id": current.id, "operation_count": 2, "summary": patch.summary})
    append_event(db, ctx, run, "validation.completed", {"status": "passed", "finding_count": 0, "patch_id": patch.id})
    append_event(db, ctx, run, "run.completed", {"status": "completed", "summary": "Approved outline continued into a cited draft proposal.", "patch_id": patch.id})
    run.status = "completed"
    run.usage_json = {**run.usage_json, "output_tokens": max(1, len(project.brief) // 4), "tool_calls": 1, "estimated_cost_usd": 0.00005}
    audit(db, ctx, "run.completed", "agent_run", run.id, "Resumed approved plan and produced content proposal")
    db.commit()
    checkpoint_local_run(settings, ctx, run, "completed", {"patch_id": patch.id, "approved_outline": True})


def retry_delegated_task(db: Session, ctx: RuntimeContext, task_id: str) -> DelegatedTask:
    """Requeue one failed specialist task without duplicating its parent run."""
    ctx.require(
        "retry delegated work",
        {"author", "reviewer", "workspace_admin", "organization_admin"},
    )
    task = db.query(DelegatedTask).filter_by(id=task_id, workspace_id=ctx.workspace_id).first()
    if not task:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The delegated task was not found.", 404)
    if task.status in {"queued", "running", "completed"}:
        return task
    attempts = int(task.result_refs.get("attempts", 0))
    if attempts >= 3:
        raise GroundloomError(
            "CONFLICT", "The delegated task reached its retry limit.", 409, retryable=False
        )
    task.status = "queued"
    task.error_code = None
    task.lease_owner = None
    task.lease_until = None
    task.result_refs = {
        **task.result_refs,
        "attempts": attempts + 1,
        "retry_requested": True,
    }
    audit(
        db,
        ctx,
        "delegated_task.retry_requested",
        "delegated_task",
        task.id,
        "Requeued bounded specialist work",
    )
    outbox(
        db,
        ctx.workspace_id,
        "DelegatedTaskRetryRequested",
        "delegated_task",
        task.id,
        {"task_id": task.id, "attempt": attempts + 1},
    )
    db.commit()
    return task


def claim_delegated_tasks(
    db: Session,
    workspace_id: str,
    worker_id: str,
    *,
    limit: int = 10,
    lease_seconds: int = 300,
) -> list[DelegatedTask]:
    now = utcnow()
    rows = (
        db.query(DelegatedTask)
        .filter(DelegatedTask.workspace_id == workspace_id)
        .filter(
            (DelegatedTask.status == "queued")
            | ((DelegatedTask.status == "running") & (DelegatedTask.lease_until < now))
        )
        .order_by(DelegatedTask.created_at)
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
        .all()
    )
    for task in rows:
        task.status = "running"
        task.lease_owner = worker_id
        task.lease_until = now + timedelta(seconds=lease_seconds)
    db.commit()
    return rows


def process_delegated_task(
    db: Session, ctx: RuntimeContext, task: DelegatedTask
) -> DelegatedTask:
    if task.workspace_id != ctx.workspace_id:
        raise GroundloomError("FORBIDDEN", "The delegated task is outside the workspace scope.", 403)
    run = db.query(AgentRun).filter_by(id=task.parent_run_id, workspace_id=ctx.workspace_id).first()
    if not run or run.project_id != task.project_id:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The parent run was not found.", 404)
    if run.cancel_requested or run.status == "cancelled":
        task.status = "cancelled"
        task.lease_owner = None
        task.lease_until = None
        db.commit()
        return task
    if task.status == "completed":
        return task
    append_event(
        db,
        ctx,
        run,
        "subagent.started",
        {"task_id": task.id, "task_type": task.task_type, "status": "running"},
    )
    # The local specialist adapter returns only bounded structured references;
    # production may replace this processor with a configured specialist model.
    task.status = "completed"
    task.result_refs = {
        **task.result_refs,
        "status": "proposal_reconciled",
        "worker": "delegated-task-worker",
    }
    task.error_code = None
    task.lease_owner = None
    task.lease_until = None
    append_event(
        db,
        ctx,
        run,
        "subagent.completed",
        {"task_id": task.id, "task_type": task.task_type, "status": "completed"},
    )
    audit(db, ctx, "delegated_task.completed", "delegated_task", task.id, "Specialist task completed")
    db.commit()
    return task


def run_delegated_worker_once(
    db: Session, ctx: RuntimeContext, worker_id: str, *, limit: int = 10
) -> dict[str, int]:
    set_tenant_context(db, ctx.workspace_id)
    touch_worker_heartbeat(db, worker_id, "delegated", ctx.workspace_id, details={"limit": limit})
    db.commit()
    claimed = claim_delegated_tasks(db, ctx.workspace_id, worker_id, limit=limit)
    completed = cancelled = failed = 0
    for task in claimed:
        try:
            result = process_delegated_task(db, ctx, task)
            if result.status == "completed":
                completed += 1
            elif result.status == "cancelled":
                cancelled += 1
        except Exception as exc:
            db.rollback()
            failed_task = db.query(DelegatedTask).filter_by(id=task.id, workspace_id=ctx.workspace_id).first()
            if failed_task:
                failed_task.status = "failed"
                failed_task.error_code = exc.code if isinstance(exc, GroundloomError) else "DELEGATED_TASK_FAILED"
                failed_task.lease_owner = None
                failed_task.lease_until = None
                audit(db, ctx, "delegated_task.failed", "delegated_task", failed_task.id, "Specialist task failed", "failure")
                db.commit()
            failed += 1
    worker_summary = {
        "claimed": len(claimed),
        "completed": completed,
        "cancelled": cancelled,
        "failed": failed,
    }
    touch_worker_heartbeat(db, worker_id, "delegated", ctx.workspace_id, details=worker_summary)
    db.commit()
    return worker_summary
def reconcile_delegated_tasks(
    db: Session, ctx: RuntimeContext, parent_run_id: str
) -> dict[str, Any]:
    """Return a durable parent-scoped summary for partial delegation recovery."""
    ctx.require(
        "reconcile delegated work",
        {"viewer", "author", "reviewer", "workspace_admin", "organization_admin"},
    )
    run = db.query(AgentRun).filter_by(id=parent_run_id, workspace_id=ctx.workspace_id).first()
    if not run:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The parent run was not found.", 404)
    tasks = (
        db.query(DelegatedTask)
        .filter_by(parent_run_id=parent_run_id, workspace_id=ctx.workspace_id)
        .order_by(DelegatedTask.created_at)
        .all()
    )
    counts = {
        status: sum(task.status == status for task in tasks)
        for status in {task.status for task in tasks}
    }
    summary = {"parent_run_id": parent_run_id, "task_count": len(tasks), "counts": counts}
    append_event(db, ctx, run, "subagent.reconciled", summary)
    audit(
        db,
        ctx,
        "delegated_task.reconciled",
        "agent_run",
        run.id,
        "Reconciled specialist task states",
    )
    db.commit()
    return summary


def add_todo(
    db: Session, ctx: RuntimeContext, run: AgentRun, description: str, status: str, sort_order: int
) -> Todo:
    todo = Todo(
        id=new_id("todo"),
        workspace_id=ctx.workspace_id,
        project_id=run.project_id,
        run_id=run.id,
        description=description,
        status=status,
        sort_order=sort_order,
    )
    db.add(todo)
    db.flush()
    append_event(
        db,
        ctx,
        run,
        "todo.updated" if sort_order else "todo.created",
        {
            "todo_id": todo.id,
            "description": description,
            "status": status,
            "sort_order": sort_order,
        },
    )
    return todo


def list_skills(db: Session, ctx: RuntimeContext) -> list[dict[str, Any]]:
    rows = (
        db.query(Skill)
        .filter((Skill.workspace_id == ctx.workspace_id) | (Skill.workspace_id.is_(None)))
        .order_by(Skill.scope, Skill.name)
        .all()
    )
    output = []
    for skill in rows:
        versions = (
            db.query(SkillVersion)
            .filter_by(skill_id=skill.id)
            .order_by(SkillVersion.version_no.desc())
            .all()
        )
        latest = versions[0] if versions else None
        output.append(
            {
                "id": skill.id,
                "slug": skill.slug,
                "name": skill.name,
                "scope": skill.scope,
                "description": latest.description if latest else "",
                "versions": [
                    {
                        "id": v.id,
                        "version_no": v.version_no,
                        "status": v.status,
                        "description": v.description,
                        "content_hash": v.content_hash,
                    }
                    for v in versions
                ],
            }
        )
    return output


def read_memory(db: Session, ctx: RuntimeContext) -> list[dict[str, Any]]:
    rows = (
        db.query(MemoryItem)
        .filter_by(workspace_id=ctx.workspace_id, user_id=ctx.user_id, status="approved")
        .order_by(MemoryItem.namespace, MemoryItem.key)
        .all()
    )
    return [
        {
            "id": row.id,
            "namespace": row.namespace,
            "key": row.key,
            "value": row.value_json,
            "status": row.status,
            "provenance": row.provenance_json,
        }
        for row in rows
    ]


def write_memory(db: Session, ctx: RuntimeContext, body: MemoryWrite) -> dict[str, Any]:
    ctx.require("write memory", {"author", "reviewer", "workspace_admin", "organization_admin"})
    value_text = str(body.value)
    if len(value_text) > 10_000 or re.search(
        r"(api[_ -]?key|password|secret|token)(\s*[:=]|\b)", value_text, re.I
    ):
        raise GroundloomError(
            "INVALID_INPUT", "Memory value is too large or contains a secret-like field.", 422
        )
    row = (
        db.query(MemoryItem)
        .filter_by(
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            namespace=body.namespace,
            key=body.key,
        )
        .first()
    )
    if row is None:
        row = MemoryItem(
            id=new_id("mem"),
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            namespace=body.namespace,
            key=body.key,
            value_json=body.value,
            provenance_json={"actor_id": ctx.user_id, "correlation_id": ctx.correlation_id},
        )
        db.add(row)
    else:
        row.value_json = body.value
        row.provenance_json = {
            "actor_id": ctx.user_id,
            "correlation_id": ctx.correlation_id,
            "updated": True,
        }
    audit(db, ctx, "memory.written", "memory_item", row.id, "Updated scoped approved memory")
    db.commit()
    return {
        "id": row.id,
        "namespace": row.namespace,
        "key": row.key,
        "value": row.value_json,
        "status": row.status,
        "provenance": row.provenance_json,
    }


def create_skill(db: Session, ctx: RuntimeContext, body: SkillCreate) -> SkillVersion:
    ctx.require("create skills", {"author", "reviewer", "workspace_admin", "organization_admin"})
    if body.scope == "organization" and "organization_admin" not in ctx.roles:
        raise GroundloomError(
            "PERMISSION_DENIED", "Organization skills require organization-admin permission.", 403
        )
    if db.query(Skill).filter_by(slug=body.slug, workspace_id=ctx.workspace_id).first():
        raise GroundloomError(
            "INVALID_INPUT", "A skill with this slug already exists in the workspace.", 422
        )
    if re.search(r"(api[_ -]?key|password|secret|token)\s*[:=]", body.content, re.I):
        raise GroundloomError("INVALID_INPUT", "Skill content appears to contain a secret.", 422)
    skill = Skill(
        id=new_id("sk"),
        workspace_id=ctx.workspace_id,
        scope=body.scope,
        slug=body.slug,
        name=body.name,
    )
    db.add(skill)
    db.flush()
    raw = f"name: {body.name}\ndescription: {body.description}\n\n{body.content}".encode()
    version = SkillVersion(
        id=new_id("skv"),
        workspace_id=ctx.workspace_id,
        skill_id=skill.id,
        version_no=1,
        status="draft",
        description=body.description,
        package_json={
            "content": body.content,
            "frontmatter": {"name": body.name, "description": body.description},
        },
        content_hash=hashlib.sha256(raw).hexdigest(),
        actor_id=ctx.user_id,
    )
    db.add(version)
    audit(
        db,
        ctx,
        "skill.draft.created",
        "skill_version",
        version.id,
        "Created an unpublished skill draft",
    )
    db.commit()
    return version


def author_skill_draft(
    db: Session,
    ctx: RuntimeContext,
    body: SkillAuthorDraftCreate,
    settings: Settings,
) -> SkillVersion:
    """Create a bounded local or model-authored draft; never publish it."""
    ctx.require("author skill drafts", {"author", "reviewer", "workspace_admin", "organization_admin"})
    draft = author_skill_package(
        settings,
        objective=body.objective,
        suggested_slug=body.suggested_slug,
        suggested_name=body.suggested_name,
    )
    slug = draft.slug
    if db.query(Skill).filter_by(slug=slug, workspace_id=ctx.workspace_id).first():
        slug = f"{slug}-draft"
    version = create_skill(
        db,
        ctx,
        SkillCreate(
            slug=slug,
            name=draft.name,
            description=draft.description,
            content=draft.content,
            scope=body.scope,
        ),
    )
    version.package_json = {
        **version.package_json,
        "generation": {
            "provider": settings.model_provider,
            "model": settings.model_name,
            "prompt_version": SKILL_AUTHOR_PROMPT_VERSION,
        },
    }
    audit(
        db,
        ctx,
        "skill.ai_draft.created",
        "skill_version",
        version.id,
        "Created draft-only skill author output",
    )
    db.commit()
    return version


def fork_skill(
    db: Session, ctx: RuntimeContext, skill_id: str, body: SkillForkCreate
) -> SkillVersion:
    """Copy an authorized published package into a new workspace draft."""
    ctx.require("fork skills", {"author", "reviewer", "workspace_admin", "organization_admin"})
    source = (
        db.query(Skill)
        .filter(
            Skill.id == skill_id,
            (Skill.workspace_id == ctx.workspace_id) | (Skill.workspace_id.is_(None)),
        )
        .first()
    )
    if source is None:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The source skill was not found.", 404)
    published = (
        db.query(SkillVersion)
        .filter_by(skill_id=source.id, status="published")
        .order_by(SkillVersion.version_no.desc())
        .first()
    )
    if published is None:
        raise GroundloomError("INVALID_STATE", "Only a published skill can be forked.", 409)
    content = published.package_json.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GroundloomError("INVALID_STATE", "The published skill has no forkable content.", 409)
    slug = body.slug or f"{source.slug}-fork"
    name = body.name or f"{source.name} (fork)"
    description = body.description or published.description
    existing = (
        db.query(Skill)
        .filter_by(workspace_id=ctx.workspace_id, slug=slug)
        .first()
    )
    if existing is not None:
        raise GroundloomError("INVALID_INPUT", "A skill with this slug already exists in the workspace.", 422)
    return create_skill(
        db,
        ctx,
        SkillCreate(
            slug=slug,
            name=name,
            description=description,
            content=content,
            scope="workspace",
        ),
    )


def repair_skill_draft(
    db: Session, ctx: RuntimeContext, version_id: str, body: SkillDraftRepair
) -> SkillVersion:
    """Create a new immutable draft version while preserving the failed version."""
    ctx.require("repair skill drafts", {"author", "reviewer", "workspace_admin", "organization_admin"})
    previous = (
        db.query(SkillVersion)
        .filter_by(id=version_id, workspace_id=ctx.workspace_id)
        .first()
    )
    if previous is None:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The skill version was not found.", 404)
    if previous.status == "published":
        raise GroundloomError(
            "INVALID_STATE", "Published skill bytes are immutable; repair a draft version instead.", 409
        )
    skill = db.query(Skill).filter_by(id=previous.skill_id, workspace_id=ctx.workspace_id).first()
    if skill is None:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The skill was not found.", 404)
    if re.search(r"(api[_ -]?key|password|secret|token)\s*[:=]", body.content, re.I):
        raise GroundloomError("INVALID_INPUT", "Skill content appears to contain a secret.", 422)
    raw = f"name: {skill.name}\ndescription: {body.description}\n\n{body.content}".encode()
    next_version = (
        db.query(func.max(SkillVersion.version_no)).filter_by(skill_id=skill.id).scalar() or 0
    ) + 1
    repaired = SkillVersion(
        id=new_id("skv"),
        workspace_id=ctx.workspace_id,
        skill_id=skill.id,
        version_no=next_version,
        status="draft",
        description=body.description,
        package_json={
            "content": body.content,
            "frontmatter": {"name": skill.name, "description": body.description},
            "repaired_from_version_id": previous.id,
        },
        content_hash=hashlib.sha256(raw).hexdigest(),
        actor_id=ctx.user_id,
    )
    db.add(repaired)
    audit(
        db,
        ctx,
        "skill.draft.repaired",
        "skill_version",
        repaired.id,
        "Created a repaired unpublished skill draft",
    )
    db.commit()
    return repaired


def validate_skill(db: Session, ctx: RuntimeContext, version_id: str) -> SkillVersion:
    version = db.query(SkillVersion).filter_by(id=version_id, workspace_id=ctx.workspace_id).first()
    if not version:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The skill version was not found.", 404)
    content = version.package_json.get("content", "")
    valid = (
        bool(version.description.strip())
        and len(content) <= 100_000
        and not re.search(r"(^|\n)\s*(sudo|rm -rf|curl\s+http)", content, re.I)
    )
    version.status = "valid" if valid else "invalid"
    audit(
        db, ctx, "skill.version.validated", "skill_version", version.id, "Validated skill package"
    )
    db.commit()
    if not valid:
        raise GroundloomError(
            "MODEL_OUTPUT_INVALID",
            "The skill package failed validation.",
            422,
            details={"status": "invalid"},
        )
    return version


def publish_skill(db: Session, ctx: RuntimeContext, version_id: str) -> SkillVersion:
    version = db.query(SkillVersion).filter_by(id=version_id, workspace_id=ctx.workspace_id).first()
    if not version:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The skill version was not found.", 404)
    if version.status not in {"valid", "approval_pending"}:
        raise GroundloomError("INVALID_STATE", "Only a valid skill version can be published.", 409)
    ctx.require("publish skills", {"workspace_admin", "organization_admin"})
    version.status = "published"
    audit(
        db,
        ctx,
        "skill.version.published",
        "skill_version",
        version.id,
        "Published immutable skill version",
    )
    outbox(
        db,
        ctx.workspace_id,
        "SkillVersionPublished",
        "skill_version",
        version.id,
        {"skill_version_id": version.id},
    )
    db.commit()
    return version


def content_blocks(
    db: Session, ctx: RuntimeContext, project_id: str, version_id: str | None = None
) -> tuple[ContentVersion, list[ContentBlock]]:
    project = _project(db, ctx, project_id)
    selected = version_id or project.current_content_version_id
    version = (
        db.query(ContentVersion)
        .filter_by(id=selected, project_id=project.id, workspace_id=ctx.workspace_id)
        .first()
        if selected
        else None
    )
    if not version:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The content version was not found.", 404)
    blocks = (
        db.query(ContentBlock)
        .filter_by(content_version_id=version.id, workspace_id=ctx.workspace_id)
        .order_by(ContentBlock.order_no)
        .all()
    )
    return version, blocks


def patch_out(patch: Patch) -> dict[str, Any]:
    return {
        "id": patch.id,
        "project_id": patch.project_id,
        "base_content_version_id": patch.base_content_version_id,
        "status": patch.status,
        "operations": patch.operations,
        "summary": patch.summary,
        "validation": patch.validation_json,
        "decision_reason": patch.decision_reason,
    }


def validate_patch_operations(
    db: Session, ctx: RuntimeContext, project_id: str, body: PatchCreate
) -> dict[str, Any]:
    version, blocks = content_blocks(db, ctx, project_id, body.base_content_version_id)
    known = {block.id for block in blocks}
    config = db.get(ProjectConfigVersion, _project(db, ctx, project_id).current_config_version_id)
    allowed_versions = set(config.source_version_ids if config else [])
    findings = []
    for operation in body.operations:
        if operation.op in {"insert_after", "replace_block"}:
            payload = operation.payload or {}
            block_type = payload.get("block_type")
            if operation.op == "replace_block" and not block_type and operation.block_id:
                existing = next((block for block in blocks if block.id == operation.block_id), None)
                block_type = existing.block_type if existing else None
            findings.extend(validate_block_payload(block_type, payload))
        if (
            operation.op in {"replace_block", "delete_block", "move_block", "replace_citations"}
            and operation.block_id not in known
        ):
            findings.append(
                {
                    "code": "UNKNOWN_BLOCK",
                    "message": "Operation references an unknown block.",
                    "block_id": operation.block_id,
                }
            )
        if (
            operation.op == "insert_after"
            and operation.after_block_id
            and operation.after_block_id not in known
        ):
            findings.append(
                {
                    "code": "UNKNOWN_ANCHOR",
                    "message": "Insert anchor is not in the base version.",
                    "block_id": operation.after_block_id,
                }
            )
        for citation in operation.citations or []:
            if citation.get("source_version_id") not in allowed_versions:
                findings.append(
                    {
                        "code": "UNAUTHORIZED_CITATION",
                        "message": "Citation is outside the pinned project source scope.",
                    }
                )
    return {
        "status": "invalid" if findings else "valid",
        "findings": findings,
        "base_version_id": version.id,
    }


def create_patch(db: Session, ctx: RuntimeContext, project_id: str, body: PatchCreate) -> Patch:
    ctx.require(
        "propose content changes", {"author", "reviewer", "workspace_admin", "organization_admin"}
    )
    if body.idempotency_key:
        existing = (
            db.query(IdempotencyRecord)
            .filter_by(workspace_id=ctx.workspace_id, key=body.idempotency_key)
            .first()
        )
        if existing:
            if existing.operation != "patch.create":
                raise GroundloomError(
                    "IDEMPOTENCY_CONFLICT",
                    "The idempotency key was used for another operation.",
                    409,
                )
            patch_id = str(existing.response_json.get("patch_id", ""))
            patch = (
                db.query(Patch)
                .filter_by(id=patch_id, workspace_id=ctx.workspace_id, project_id=project_id)
                .first()
            )
            if patch is None:
                raise GroundloomError(
                    "INTERNAL_ERROR",
                    "The idempotent patch record is incomplete.",
                    500,
                )
            return patch
    validation = validate_patch_operations(db, ctx, project_id, body)
    if validation["status"] != "valid":
        raise GroundloomError(
            "MODEL_OUTPUT_INVALID",
            "The proposed patch failed deterministic validation.",
            422,
            details=validation,
        )
    patch = Patch(
        id=new_id("pat"),
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        base_content_version_id=body.base_content_version_id,
        status="presented",
        operations=[op.model_dump(exclude_none=True) for op in body.operations],
        summary=body.summary,
        validation_json=validation,
        actor_id=ctx.user_id,
    )
    db.add(patch)
    db.flush()
    remember_idempotency(
        db,
        ctx,
        body.idempotency_key,
        "patch.create",
        {"patch_id": patch.id},
    )
    audit(db, ctx, "patch.proposed", "patch", patch.id, "Created a validated non-canonical patch")
    db.commit()
    return patch


def accept_patch(
    db: Session, ctx: RuntimeContext, patch_id: str, body: DecisionIn
) -> tuple[Patch, ContentVersion]:
    ctx.require("accept content changes", {"reviewer", "workspace_admin", "organization_admin"})
    patch = db.query(Patch).filter_by(id=patch_id, workspace_id=ctx.workspace_id).first()
    if not patch:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The patch was not found.", 404)
    if patch.status == "accepted":
        version = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.parent_version_id == patch.base_content_version_id,
                ContentVersion.project_id == patch.project_id,
            )
            .order_by(ContentVersion.version_no.desc())
            .first()
        )
        if not version:
            raise GroundloomError(
                "INTERNAL_ERROR", "Accepted patch is missing its content version.", 500
            )
        return patch, version
    if patch.status != "presented":
        raise GroundloomError("INVALID_STATE", "Only a presented patch can be accepted.", 409)
    validation = validate_patch_operations(
        db,
        ctx,
        patch.project_id,
        PatchCreate(
            base_content_version_id=patch.base_content_version_id,
            operations=patch.operations,
            summary=patch.summary,
        ),
    )
    if validation["status"] != "valid":
        raise GroundloomError(
            "INVALID_PROPOSAL",
            "The proposal no longer satisfies the typed content contract.",
            422,
            details=validation,
        )
    project = _project(db, ctx, patch.project_id)
    if (
        project.current_content_version_id != body.expected_current_version_id
        or body.expected_current_version_id != patch.base_content_version_id
    ):
        patch.status = "conflicted"
        audit(
            db,
            ctx,
            "patch.conflicted",
            "patch",
            patch.id,
            "Patch base version is stale",
            "conflict",
        )
        db.commit()
        raise GroundloomError(
            "VERSION_CONFLICT",
            "The content changed since this proposal was created. Refresh and review the new base.",
            409,
            details={"current_version_id": project.current_content_version_id},
        )
    base, base_blocks = content_blocks(db, ctx, project.id, patch.base_content_version_id)
    new_version_no = (
        db.query(func.max(ContentVersion.version_no)).filter_by(project_id=project.id).scalar() or 0
    ) + 1
    new_version = ContentVersion(
        id=new_id("cv"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        version_no=new_version_no,
        status="accepted",
        parent_version_id=base.id,
        provenance_json={
            "accepted_patch_id": patch.id,
            "actor_id": ctx.user_id,
            "pinned_source_version_ids": (
                config.source_version_ids
                if (config := db.get(ProjectConfigVersion, project.current_config_version_id))
                else []
            ),
        },
    )
    db.add(new_version)
    db.flush()
    new_blocks = [
        {
            "id": block.id,
            "block_type": block.block_type,
            "order_no": block.order_no,
            "payload": block.payload,
            "citations": block.citations,
        }
        for block in base_blocks
    ]
    for operation in patch.operations:
        if operation["op"] == "replace_block":
            for item in new_blocks:
                if item["id"] == operation.get("block_id"):
                    payload = operation.get("payload") or {}
                    item["payload"] = payload
                    item["block_type"] = payload.get("block_type", item["block_type"])
        elif operation["op"] == "delete_block":
            new_blocks = [item for item in new_blocks if item["id"] != operation.get("block_id")]
        elif operation["op"] == "replace_citations":
            for item in new_blocks:
                if item["id"] == operation.get("block_id"):
                    item["citations"] = operation.get("citations") or []
        elif operation["op"] == "insert_after":
            payload = operation.get("payload") or {"block_type": "paragraph", "text": ""}
            new_item = {
                "id": new_id("blk"),
                "block_type": payload.get("block_type", "paragraph"),
                "order_no": 0,
                "payload": payload,
                "citations": payload.get("citations", []),
            }
            anchor = operation.get("after_block_id")
            if anchor:
                index = next(
                    (i for i, item in enumerate(new_blocks) if item["id"] == anchor),
                    len(new_blocks),
                )
                new_blocks.insert(index + 1, new_item)
            else:
                new_blocks.append(new_item)
        elif operation["op"] == "move_block":
            moving = next(
                (item for item in new_blocks if item["id"] == operation.get("block_id")), None
            )
            if moving:
                new_blocks.remove(moving)
                index = next(
                    (
                        i
                        for i, item in enumerate(new_blocks)
                        if item["id"] == operation.get("after_block_id")
                    ),
                    len(new_blocks) - 1,
                )
                new_blocks.insert(max(index + 1, 0), moving)
    for order, item in enumerate(new_blocks):
        db.add(
            ContentBlock(
                id=item["id"],
                workspace_id=ctx.workspace_id,
                content_version_id=new_version.id,
                block_type=item["block_type"],
                order_no=order,
                payload=item["payload"],
                citations=item["citations"],
            )
        )
    project.current_content_version_id = new_version.id
    patch.status = "accepted"
    patch.decision_reason = body.reason
    audit(
        db,
        ctx,
        "patch.accepted",
        "patch",
        patch.id,
        "Accepted patch into one immutable content version",
    )
    outbox(
        db,
        ctx.workspace_id,
        "PatchAccepted",
        "patch",
        patch.id,
        {"patch_id": patch.id, "content_version_id": new_version.id},
    )
    db.commit()
    return patch, new_version


def reject_patch(db: Session, ctx: RuntimeContext, patch_id: str, reason: str | None) -> Patch:
    ctx.require("reject content changes", {"reviewer", "workspace_admin", "organization_admin"})
    patch = db.query(Patch).filter_by(id=patch_id, workspace_id=ctx.workspace_id).first()
    if not patch:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The patch was not found.", 404)
    if patch.status in {"rejected", "superseded"}:
        return patch
    if patch.status != "presented":
        raise GroundloomError("INVALID_STATE", "Only a presented patch can be rejected.", 409)
    patch.status = "rejected"
    patch.decision_reason = reason
    audit(
        db,
        ctx,
        "patch.rejected",
        "patch",
        patch.id,
        "Rejected proposal; canonical content unchanged",
    )
    outbox(db, ctx.workspace_id, "PatchRejected", "patch", patch.id, {"patch_id": patch.id})
    db.commit()
    return patch


def accept_outline(db: Session, ctx: RuntimeContext, outline_id: str) -> OutlineVersion:
    ctx.require("approve outlines", {"author", "reviewer", "workspace_admin", "organization_admin"})
    outline = (
        db.query(OutlineVersion).filter_by(id=outline_id, workspace_id=ctx.workspace_id).first()
    )
    if not outline:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The outline was not found.", 404)
    outline.status = "accepted"
    audit(db, ctx, "outline.accepted", "outline_version", outline.id, "Accepted proposed outline")
    db.commit()
    return outline


def validate_content(
    db: Session,
    ctx: RuntimeContext,
    project_id: str,
    version_id: str | None = None,
    settings: Settings | None = None,
) -> ValidationRun:
    ctx.require(
        "validate content",
        {"viewer", "author", "reviewer", "workspace_admin", "organization_admin"},
    )
    version, blocks = content_blocks(db, ctx, project_id, version_id)
    findings: list[dict[str, Any]] = []
    for block in blocks:
        for payload_finding in validate_block_payload(block.block_type, block.payload):
            findings.append(
                {
                    "severity": "error",
                    "category": "structure",
                    "block_id": block.id,
                    "code": payload_finding["code"],
                    "message": payload_finding["message"],
                }
            )
        payload = block.payload if isinstance(block.payload, dict) else {}
        if block.block_type == "paragraph" and payload.get("text") and not block.citations:
            findings.append(
                {
                    "severity": "warning",
                    "category": "citation",
                    "block_id": block.id,
                    "message": "Paragraph has no citation; mark unsupported claims or add evidence.",
                }
            )
    draft_text = "\n\n".join(
        str(block.payload.get("text", ""))
        for block in blocks
        if isinstance(block.payload, dict)
    )[:20_000]
    citations = [
        str(citation.get("passage_id", citation) if isinstance(citation, dict) else citation)
        for block in blocks
        for citation in (block.citations or [])[:20]
    ][:100]
    grader = build_grader(settings)
    rubric = RubricVersion("groundloom.semantic.v1", require_citations=True, minimum_score=0.75)
    grade = grader.grade(draft_text, citations, rubric)
    for feedback in grade.feedback:
        findings.append(
            {
                "severity": "warning" if grade.verdict == "needs_revision" else "info",
                "category": "semantic",
                "block_id": None,
                "message": feedback,
            }
        )
    semantic_summary = {
        "rubric_id": grade.rubric_id,
        "score": grade.score,
        "verdict": grade.verdict,
        "feedback": list(grade.feedback),
        "provider": getattr(grader, "provider_id", "unknown"),
        "model": getattr(grader, "model", "unknown"),
    }
    validation = ValidationRun(
        id=new_id("val"),
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        content_version_id=version.id,
        status=(
            "failed"
            if any(f["severity"] == "error" for f in findings)
            or grade.verdict == "needs_revision"
            else "passed"
        ),
        summary_json={
            "finding_count": len(findings),
            "error_count": sum(1 for f in findings if f["severity"] == "error"),
            "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
            "semantic": semantic_summary,
        },
    )
    db.add(validation)
    db.flush()
    for finding in findings:
        db.add(
            ValidationFinding(
                id=new_id("finding"),
                workspace_id=ctx.workspace_id,
                validation_run_id=validation.id,
                severity=finding["severity"],
                category=finding["category"],
                block_id=finding.get("block_id"),
                message=finding["message"],
                evidence_json={},
            )
        )
    audit(
        db,
        ctx,
        "content.validated",
        "content_version",
        version.id,
        "Ran deterministic and semantic content validation",
    )
    db.commit()
    return validation


def validation_dto(db: Session, validation: ValidationRun) -> dict[str, Any]:
    findings = db.query(ValidationFinding).filter_by(validation_run_id=validation.id).all()
    return {
        "id": validation.id,
        "content_version_id": validation.content_version_id,
        "status": validation.status,
        "summary": validation.summary_json,
        "findings": [
            {
                "id": f.id,
                "severity": f.severity,
                "category": f.category,
                "block_id": f.block_id,
                "message": f.message,
                "status": f.status,
            }
            for f in findings
        ],
    }


def export_content(
    db: Session, ctx: RuntimeContext, settings: Settings, body: ExportCreate
) -> ExportJob:
    ctx.require("export content", {"author", "reviewer", "workspace_admin", "organization_admin"})
    project = _project(db, ctx, body.project_id)
    version, _blocks = content_blocks(db, ctx, project.id, body.content_version_id)
    key = body.idempotency_key or f"export:{project.id}:{version.id}:{body.format}"
    existing = (
        db.query(ExportJob).filter_by(workspace_id=ctx.workspace_id, idempotency_key=key).first()
    )
    if existing:
        return existing
    job = ExportJob(
        id=new_id("exp"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        content_version_id=version.id,
        format=body.format,
        status="queued",
        idempotency_key=key,
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(job)
    db.flush()
    audit(db, ctx, "export.requested", "export_job", job.id, "Queued immutable content export")
    outbox(
        db,
        ctx.workspace_id,
        "ExportRequested",
        "export_job",
        job.id,
        {"export_id": job.id, "content_version_id": version.id, "format": body.format},
    )
    db.commit()
    # The local adapter keeps the single-process quickstart usable. Staging and
    # production leave the durable job queued for the export worker.
    if settings.export_inline_local is not False and settings.env in {"development", "test"}:
        run_export_worker_once(db, ctx, settings, "inline-local", limit=1)
        job = db.query(ExportJob).filter_by(id=job.id, workspace_id=ctx.workspace_id).one()
    return job


def claim_export_jobs(
    db: Session,
    workspace_id: str,
    worker_id: str,
    *,
    limit: int = 10,
    lease_seconds: int = 300,
) -> list[ExportJob]:
    now = utcnow()
    rows = (
        db.query(ExportJob)
        .filter(ExportJob.workspace_id == workspace_id)
        .filter(
            (ExportJob.status == "queued")
            | ((ExportJob.status == "rendering") & (ExportJob.lease_until < now))
        )
        .order_by(ExportJob.created_at)
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        row.status = "rendering"
        row.lease_owner = worker_id
        row.lease_until = now + timedelta(seconds=lease_seconds)
        row.attempts += 1
    db.commit()
    return rows


def process_export_job(
    db: Session, ctx: RuntimeContext, settings: Settings, job: ExportJob
) -> ExportJob:
    if job.workspace_id != ctx.workspace_id:
        raise GroundloomError("FORBIDDEN", "The export job is outside the workspace scope.", 403)
    if job.status == "completed" and job.object_key:
        return job
    project = _project(db, ctx, job.project_id)
    version, blocks = content_blocks(db, ctx, project.id, job.content_version_id)
    job.status = "storing"
    suffix = {"md": "md", "html": "html", "pdf": "pdf", "docx": "docx"}[job.format]
    object_key = f"workspaces/{ctx.workspace_id}/exports/{job.id}.{suffix}"
    build_object_store(settings).put_bytes(object_key, render_content(project.name, blocks, job.format))
    job.object_key = object_key
    job.status = "completed"
    job.error_code = None
    job.lease_owner = None
    job.lease_until = None
    audit(db, ctx, "export.completed", "export_job", job.id, "Rendered immutable content version")
    outbox(
        db,
        ctx.workspace_id,
        "ExportCompleted",
        "export_job",
        job.id,
        {"export_id": job.id, "content_version_id": version.id, "format": job.format},
    )
    db.commit()
    return job


def run_export_worker_once(
    db: Session,
    ctx: RuntimeContext,
    settings: Settings,
    worker_id: str,
    *,
    limit: int = 10,
) -> dict[str, int]:
    set_tenant_context(db, ctx.workspace_id)
    touch_worker_heartbeat(db, worker_id, "export", ctx.workspace_id, details={"limit": limit})
    db.commit()
    claimed = claim_export_jobs(db, ctx.workspace_id, worker_id, limit=limit)
    completed = 0
    failed = 0
    for job in claimed:
        try:
            process_export_job(db, ctx, settings, job)
            completed += 1
        except Exception as exc:
            db.rollback()
            failed_job = db.query(ExportJob).filter_by(id=job.id, workspace_id=ctx.workspace_id).first()
            if failed_job:
                failed_job.status = "failed"
                failed_job.error_code = exc.code if isinstance(exc, GroundloomError) else "EXPORT_FAILED"
                failed_job.lease_owner = None
                failed_job.lease_until = None
                audit(db, ctx, "export.failed", "export_job", failed_job.id, "Export worker failed")
                outbox(
                    db,
                    ctx.workspace_id,
                    "ExportFailed",
                    "export_job",
                    failed_job.id,
                    {"export_id": failed_job.id, "error_code": failed_job.error_code},
                )
                db.commit()
            failed += 1
    result = {"claimed": len(claimed), "completed": completed, "failed": failed}
    touch_worker_heartbeat(db, worker_id, "export", ctx.workspace_id, details=result)
    db.commit()
    return result


def ensure_workspace_preferences(db: Session, workspace_id: str) -> WorkspacePreference:
    preferences = db.get(WorkspacePreference, workspace_id)
    if not preferences:
        preferences = WorkspacePreference(workspace_id=workspace_id)
        db.add(preferences)
        db.flush()
    return preferences


def workspace_preferences_dto(preferences: WorkspacePreference) -> dict[str, Any]:
    return {
        "workspace_id": preferences.workspace_id,
        "version_no": preferences.version_no,
        "review_ai_edits": preferences.review_ai_edits,
        "require_citations": preferences.require_citations,
        "default_export": preferences.default_export,
        "require_plan_approval": preferences.require_plan_approval,
        "daily_token_budget": preferences.daily_token_budget,
        "daily_cost_budget_usd": preferences.daily_cost_budget_usd,
        "updated_at": preferences.updated_at.isoformat(),
    }


def get_workspace_preferences(db: Session, ctx: RuntimeContext) -> dict[str, Any]:
    ctx.require(
        "read workspace preferences",
        {"viewer", "author", "reviewer", "workspace_admin", "organization_admin"},
    )
    preferences = ensure_workspace_preferences(db, ctx.workspace_id)
    db.commit()
    return workspace_preferences_dto(preferences)


def update_workspace_preferences(
    db: Session, ctx: RuntimeContext, body: WorkspacePreferencesUpdate
) -> dict[str, Any]:
    ctx.require("update workspace preferences", {"workspace_admin", "organization_admin"})
    preferences = ensure_workspace_preferences(db, ctx.workspace_id)
    preferences.review_ai_edits = body.review_ai_edits
    preferences.require_citations = body.require_citations
    preferences.default_export = body.default_export
    preferences.require_plan_approval = body.require_plan_approval
    preferences.daily_token_budget = body.daily_token_budget
    preferences.daily_cost_budget_usd = body.daily_cost_budget_usd
    preferences.version_no += 1
    audit(
        db,
        ctx,
        "workspace.preferences.updated",
        "workspace_preferences",
        ctx.workspace_id,
        "Updated typed workspace preferences",
    )
    outbox(
        db,
        ctx.workspace_id,
        "WorkspacePreferencesUpdated",
        "workspace",
        ctx.workspace_id,
        {"workspace_id": ctx.workspace_id, "version_no": preferences.version_no},
    )
    db.commit()
    return workspace_preferences_dto(preferences)


def ensure_retention_policy(db: Session, workspace_id: str) -> RetentionPolicy:
    policy = db.get(RetentionPolicy, workspace_id)
    if not policy:
        policy = RetentionPolicy(workspace_id=workspace_id)
        db.add(policy)
        db.flush()
    return policy


def retention_policy_dto(policy: RetentionPolicy) -> dict[str, Any]:
    return {
        "workspace_id": policy.workspace_id,
        "sources_days": policy.sources_days,
        "projects_days": policy.projects_days,
        "agent_data_days": policy.agent_data_days,
        "exports_days": policy.exports_days,
        "audit_days": policy.audit_days,
        "legal_hold": policy.legal_hold,
    }


def get_retention_policy(db: Session, ctx: RuntimeContext) -> dict[str, Any]:
    ctx.require(
        "read retention policy",
        {"viewer", "author", "reviewer", "workspace_admin", "organization_admin"},
    )
    policy = ensure_retention_policy(db, ctx.workspace_id)
    db.commit()
    return retention_policy_dto(policy)


def update_retention_policy(
    db: Session, ctx: RuntimeContext, body: RetentionPolicyUpdate
) -> dict[str, Any]:
    ctx.require("update retention policy", {"workspace_admin", "organization_admin"})
    policy = ensure_retention_policy(db, ctx.workspace_id)
    policy.sources_days = body.sources_days
    policy.projects_days = body.projects_days
    policy.agent_data_days = body.agent_data_days
    policy.exports_days = body.exports_days
    policy.audit_days = body.audit_days
    policy.legal_hold = body.legal_hold
    audit(
        db,
        ctx,
        "retention.policy.updated",
        "retention_policy",
        ctx.workspace_id,
        "Updated workspace retention policy",
    )
    outbox(
        db,
        ctx.workspace_id,
        "RetentionPolicyUpdated",
        "workspace",
        ctx.workspace_id,
        {"workspace_id": ctx.workspace_id, "legal_hold": policy.legal_hold},
    )
    db.commit()
    return retention_policy_dto(policy)


def request_project_deletion(
    db: Session, ctx: RuntimeContext, project_id: str, idempotency_key: str | None = None
) -> DeletionRequest:
    ctx.require("request project deletion", {"workspace_admin", "organization_admin"})
    project = _project(db, ctx, project_id)
    existing = None
    if idempotency_key:
        existing = (
            db.query(DeletionRequest)
            .filter_by(workspace_id=ctx.workspace_id, idempotency_key=idempotency_key)
            .first()
        )
    if existing:
        return existing
    existing = (
        db.query(DeletionRequest)
        .filter_by(workspace_id=ctx.workspace_id, scope_type="project", resource_id=project.id)
        .filter(DeletionRequest.status.in_(["pending", "running", "blocked"]))
        .first()
    )
    if existing:
        return existing
    ensure_retention_policy(db, ctx.workspace_id)
    request = DeletionRequest(
        id=new_id("del"),
        workspace_id=ctx.workspace_id,
        scope_type="project",
        resource_id=project.id,
        requested_by=ctx.user_id,
        status="pending",
        idempotency_key=idempotency_key,
        step_status={"canonical": "pending", "objects": "pending", "checkpoints": "pending"},
    )
    db.add(request)
    project.status = "deletion_pending"
    for run in db.query(AgentRun).filter_by(project_id=project.id, workspace_id=ctx.workspace_id).all():
        if run.status in {"queued", "running", "waiting_for_user", "waiting_for_approval"}:
            run.cancel_requested = True
    audit(db, ctx, "retention.deletion.requested", "project", project.id, "Project deletion queued")
    outbox(
        db,
        ctx.workspace_id,
        "RetentionDeletionRequested",
        "deletion_request",
        request.id,
        {"request_id": request.id, "scope_type": request.scope_type, "resource_id": project.id},
    )
    db.commit()
    return request


def claim_deletion_requests(
    db: Session,
    workspace_id: str,
    worker_id: str,
    *,
    limit: int = 10,
    lease_seconds: int = 300,
) -> list[DeletionRequest]:
    now = utcnow()
    rows = (
        db.query(DeletionRequest)
        .filter(DeletionRequest.workspace_id == workspace_id)
        .filter(
            (DeletionRequest.status == "pending")
            | (
                (DeletionRequest.status == "running")
                & (DeletionRequest.lease_until < now)
                & (DeletionRequest.attempts < 3)
            )
        )
        .order_by(DeletionRequest.created_at)
        .limit(max(1, min(limit, 100)))
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        row.status = "running"
        row.lease_owner = worker_id
        row.lease_until = now + timedelta(seconds=lease_seconds)
        row.attempts += 1
    db.commit()
    return rows


def _delete_project_records(db: Session, ctx: RuntimeContext, project: Project) -> None:
    config_versions = db.query(ProjectConfigVersion).filter_by(
        project_id=project.id, workspace_id=ctx.workspace_id
    ).all()
    selected_source_version_ids = {
        source_version_id
        for config in config_versions
        for source_version_id in (config.source_version_ids or [])
    }
    content_version_ids = [
        row.id
        for row in db.query(ContentVersion).filter_by(
            project_id=project.id, workspace_id=ctx.workspace_id
        ).all()
    ]
    validation_ids = [
        row.id
        for row in db.query(ValidationRun).filter_by(
            project_id=project.id, workspace_id=ctx.workspace_id
        ).all()
    ]
    if validation_ids:
        db.query(ValidationFinding).filter(ValidationFinding.validation_run_id.in_(validation_ids)).delete(
            synchronize_session=False
        )
    if content_version_ids:
        db.query(ContentBlock).filter(ContentBlock.content_version_id.in_(content_version_ids)).delete(
            synchronize_session=False
        )
    db.query(ValidationRun).filter(ValidationRun.id.in_(validation_ids)).delete(synchronize_session=False)
    db.query(ContentVersion).filter(ContentVersion.id.in_(content_version_ids)).delete(
        synchronize_session=False
    )
    db.query(PublicEvent).filter_by(project_id=project.id, workspace_id=ctx.workspace_id).delete(
        synchronize_session=False
    )
    all_configs = (
        db.query(ProjectConfigVersion)
        .filter_by(workspace_id=ctx.workspace_id)
        .filter(ProjectConfigVersion.project_id != project.id)
        .all()
    )
    shared_ids = {
        version_id
        for config in all_configs
        for version_id in (config.source_version_ids or [])
    }
    for model in (Todo, DelegatedTask, Patch, AgentRun, ProjectConfigVersion, OutlineVersion, ExportJob):
        db.query(model).filter_by(project_id=project.id, workspace_id=ctx.workspace_id).delete(
            synchronize_session=False
        )
    db.query(AgentThread).filter_by(project_id=project.id, workspace_id=ctx.workspace_id).delete(
        synchronize_session=False
    )
    # Source versions are immutable and may be selected by another project;
    # delete only unshared versions and their rebuildable index rows.
    removable_ids = selected_source_version_ids - shared_ids
    if removable_ids:
        db.query(SourceChunk).filter(SourceChunk.source_version_id.in_(removable_ids)).delete(
            synchronize_session=False
        )
        db.query(SourceBlock).filter(SourceBlock.source_version_id.in_(removable_ids)).delete(
            synchronize_session=False
        )
        source_versions = db.query(SourceVersion).filter(SourceVersion.id.in_(removable_ids)).all()
        source_ids = {version.source_id for version in source_versions}
        db.query(IngestionJob).filter(IngestionJob.source_version_id.in_(removable_ids)).delete(
            synchronize_session=False
        )
        db.query(SourceVersion).filter(SourceVersion.id.in_(removable_ids)).delete(
            synchronize_session=False
        )
        for source_id in source_ids:
            source = db.query(Source).filter_by(id=source_id, workspace_id=ctx.workspace_id).first()
            if source:
                remaining = (
                    db.query(SourceVersion)
                    .filter_by(source_id=source_id, workspace_id=ctx.workspace_id)
                    .order_by(SourceVersion.version_no.desc())
                    .first()
                )
                if remaining:
                    source.current_version_id = remaining.id
                else:
                    db.delete(source)
    db.delete(project)


def process_deletion_request(
    db: Session, ctx: RuntimeContext, settings: Settings, request: DeletionRequest
) -> DeletionRequest:
    if request.workspace_id != ctx.workspace_id:
        raise GroundloomError("FORBIDDEN", "The deletion request is outside the workspace scope.", 403)
    policy = ensure_retention_policy(db, ctx.workspace_id)
    if policy.legal_hold:
        request.status = "blocked"
        request.error_code = "LEGAL_HOLD"
        request.step_status = {**request.step_status, "legal_hold": "blocked"}
        request.lease_owner = None
        request.lease_until = None
        audit(db, ctx, "retention.deletion.blocked", "deletion_request", request.id, "Deletion blocked by legal hold", "blocked")
        db.commit()
        return request
    project = db.query(Project).filter_by(id=request.resource_id, workspace_id=ctx.workspace_id).first()
    if not project:
        request.status = "completed"
        request.completed_at = utcnow()
        request.step_status = {**request.step_status, "canonical": "completed", "objects": "completed", "checkpoints": "completed"}
        request.lease_owner = None
        request.lease_until = None
        db.commit()
        return request
    selected_source_version_ids = {
        source_version_id
        for config in db.query(ProjectConfigVersion)
        .filter_by(project_id=project.id, workspace_id=ctx.workspace_id)
        .all()
        for source_version_id in (config.source_version_ids or [])
    }
    shared_source_version_ids = {
        source_version_id
        for config in db.query(ProjectConfigVersion)
        .filter(
            ProjectConfigVersion.workspace_id == ctx.workspace_id,
            ProjectConfigVersion.project_id != project.id,
        )
        .all()
        for source_version_id in (config.source_version_ids or [])
    }
    removable_source_version_ids = selected_source_version_ids - shared_source_version_ids
    source_versions = (
        db.query(SourceVersion)
        .filter(
            SourceVersion.workspace_id == ctx.workspace_id,
            SourceVersion.id.in_(removable_source_version_ids),
        )
        .all()
        if removable_source_version_ids
        else []
    )
    export_keys = [
        row.object_key
        for row in db.query(ExportJob).filter_by(project_id=project.id, workspace_id=ctx.workspace_id).all()
        if row.object_key
    ]
    object_keys = [row.object_key for row in source_versions] + export_keys
    try:
        store = build_object_store(settings)
        for key in object_keys:
            store.delete_bytes(key)
        request.step_status = {**request.step_status, "objects": "completed"}
        checkpoint_dir = (
            settings.object_store_path / "workspaces" / ctx.workspace_id / "checkpoints" / project.id
        ).resolve()
        root = settings.object_store_path.resolve()
        if root in checkpoint_dir.parents and checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
        request.step_status = {**request.step_status, "checkpoints": "completed"}
        _delete_project_records(db, ctx, project)
        request.step_status = {**request.step_status, "canonical": "completed"}
        request.status = "completed"
        request.completed_at = utcnow()
        request.error_code = None
        request.lease_owner = None
        request.lease_until = None
        audit(db, ctx, "retention.deletion.completed", "deletion_request", request.id, "Project deletion completed")
        outbox(
            db,
            ctx.workspace_id,
            "RetentionDeletionCompleted",
            "deletion_request",
            request.id,
            {"request_id": request.id, "scope_type": request.scope_type},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = db.query(DeletionRequest).filter_by(id=request.id, workspace_id=ctx.workspace_id).one()
        failed.status = "failed"
        failed.error_code = exc.code if isinstance(exc, GroundloomError) else "DELETE_FAILED"
        failed.lease_owner = None
        failed.lease_until = None
        audit(db, ctx, "retention.deletion.failed", "deletion_request", request.id, "Deletion workflow failed", "failure")
        db.commit()
    return db.query(DeletionRequest).filter_by(id=request.id, workspace_id=ctx.workspace_id).one()


def run_deletion_worker_once(
    db: Session, ctx: RuntimeContext, settings: Settings, worker_id: str, *, limit: int = 10
) -> dict[str, int]:
    set_tenant_context(db, ctx.workspace_id)
    touch_worker_heartbeat(db, worker_id, "retention", ctx.workspace_id, details={"limit": limit})
    db.commit()
    claimed = claim_deletion_requests(db, ctx.workspace_id, worker_id, limit=limit)
    completed = blocked = failed = 0
    for request in claimed:
        result = process_deletion_request(db, ctx, settings, request)
        if result.status == "completed":
            completed += 1
        elif result.status == "blocked":
            blocked += 1
        elif result.status == "failed":
            failed += 1
    worker_summary = {"claimed": len(claimed), "completed": completed, "blocked": blocked, "failed": failed}
    touch_worker_heartbeat(db, worker_id, "retention", ctx.workspace_id, details=worker_summary)
    db.commit()
    return worker_summary
