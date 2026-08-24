import json
from collections.abc import Generator

from fastapi import Depends, FastAPI, File, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from .auth import verify_context_token
from .config import Settings, get_settings
from .context import RuntimeContext, resolve_context
from .db import build_session_factory, init_database
from .errors import GroundloomError
from .migrations import apply_migrations
from .models import (
    AgentRun,
    AgentThread,
    DeletionRequest,
    ExportJob,
    IdempotencyRecord,
    IndexRebuildJob,
    OutlineVersion,
    Patch,
    Project,
    PublicEvent,
    Skill,
)
from .object_store import build_object_store
from .schemas import (
    ApprovalDecision,
    ApprovalOut,
    DecisionIn,
    DeletionRequestCreate,
    DeletionRequestOut,
    ErrorBody,
    EventOut,
    EvidenceBundle,
    ExportCreate,
    ExportOut,
    HealthResponse,
    IndexRebuildOut,
    LivenessResponse,
    MemoryWrite,
    MessageCreate,
    PatchCreate,
    PatchOut,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    ReadinessResponse,
    RetentionPolicyOut,
    RetentionPolicyUpdate,
    RunOut,
    SkillAuthorDraftCreate,
    SkillCreate,
    SkillVersionOut,
    SourceOut,
    UploadFinalize,
    ValidationOut,
    WorkspacePreferencesOut,
    WorkspacePreferencesUpdate,
)
from .services import (
    accept_outline,
    accept_patch,
    author_skill_draft,
    content_blocks,
    create_patch,
    create_project,
    create_skill,
    execute_agent_turn,
    export_content,
    get_retention_policy,
    get_workspace_preferences,
    list_run_approvals,
    list_skills,
    list_sources,
    operational_snapshot,
    patch_out,
    project_detail,
    project_dto,
    publish_skill,
    read_memory,
    read_passage,
    reconcile_delegated_tasks,
    reject_patch,
    remember_idempotency,
    request_index_rebuild,
    request_project_deletion,
    resolve_approval,
    retry_delegated_task,
    search_evidence,
    seed_local,
    start_run,
    update_retention_policy,
    update_workspace_preferences,
    upload_source,
    validate_content,
    validate_skill,
    validation_dto,
    write_memory,
)
from .telemetry import build_telemetry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_runtime()
    apply_migrations(settings.database_url)
    db_engine = init_database(settings.database_url)
    session_factory = build_session_factory(settings.database_url, db_engine)
    with session_factory() as db:
        seed_local(db, settings)
    app = FastAPI(
        title="Groundloom API",
        version="0.1.0",
        description="Source-grounded knowledge production studio",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.db_engine = db_engine
    app.state.telemetry = build_telemetry(
        settings.telemetry_provider,
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        settings.langfuse_host,
    )
    app.state.object_store = build_object_store(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GroundloomError)
    async def groundloom_error_handler(request: Request, exc: GroundloomError):
        correlation_id = request.headers.get("X-Correlation-ID", "corr_unknown")
        request.app.state.telemetry.emit(
            "http.domain_error",
            {"route": request.url.path, "code": exc.code, "status_code": exc.status_code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorBody(
                code=exc.code,
                message=exc.message,
                correlation_id=correlation_id,
                retryable=exc.retryable,
                details=exc.details,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):
        request.app.state.telemetry.emit(
            "http.internal_error",
            {"route": request.url.path, "error_class": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content=ErrorBody(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
                correlation_id=request.headers.get("X-Correlation-ID", "corr_unknown"),
            ).model_dump(),
        )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.headers.get("X-Correlation-ID", "corr_local")
        request.app.state.telemetry.emit(
            "http.request",
            {"route": request.url.path, "method": request.method, "status_code": response.status_code},
        )
        return response

    return register_routes(app)


def get_db(request: Request) -> Generator[Session, None, None]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_ctx(
    request: Request,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> RuntimeContext:
    settings: Settings = request.app.state.settings
    if settings.env in {"staging", "production"} or settings.auth_mode == "hmac":
        x_user_id, x_workspace_id = verify_context_token(
            request.headers.get("Authorization"), settings.auth_secret
        )
    return resolve_context(db, settings, x_user_id, x_workspace_id, x_correlation_id)


def register_routes(app: FastAPI) -> FastAPI:
    def _health_snapshot(request: Request, db: Session) -> dict:
        settings: Settings = request.app.state.settings
        try:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            database = "ok"
        except Exception:
            database = "degraded"
        object_store = "ok" if request.app.state.object_store.health() else "degraded"
        operational = operational_snapshot(db, settings)
        return {
            "status": "ok" if database == object_store == "ok" else "degraded",
            "database": database,
            "object_store": object_store,
            "model_provider": settings.model_provider,
            "version": "0.1.0",
            **operational,
        }

    @app.get("/live", response_model=LivenessResponse)
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", response_model=ReadinessResponse)
    def ready(request: Request, db: Session = Depends(get_db)):
        snapshot = _health_snapshot(request, db)
        if snapshot["status"] != "ok":
            return JSONResponse(status_code=503, content=snapshot)
        return snapshot

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request, db: Session = Depends(get_db)):
        return _health_snapshot(request, db)

    @app.get("/v1/projects", response_model=list[ProjectOut])
    def projects(db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)):
        return [
            project_dto(db, p)
            for p in db.query(Project)
            .filter_by(workspace_id=ctx.workspace_id)
            .order_by(Project.updated_at.desc())
            .all()
        ]

    @app.post("/v1/projects", response_model=ProjectOut, status_code=201)
    def projects_create(
        body: ProjectCreate,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if idempotency_key:
            existing = (
                db.query(IdempotencyRecord)
                .filter_by(workspace_id=ctx.workspace_id, key=idempotency_key)
                .first()
            )
            if existing:
                if existing.operation != "project.create":
                    raise GroundloomError(
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was used for another operation.",
                        409,
                    )
                return existing.response_json
        project = create_project(db, ctx, body, request.app.state.settings)
        response = project_dto(db, project)
        response = remember_idempotency(db, ctx, idempotency_key, "project.create", response)
        db.commit()
        return response

    @app.get("/v1/projects/{project_id}", response_model=ProjectDetail)
    def project_get(
        project_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        return project_detail(db, ctx, project_id)

    @app.post("/v1/projects/{project_id}/threads/messages", response_model=RunOut, status_code=202)
    def message_send(
        project_id: str,
        body: MessageCreate,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        ctx.require(
            "message the project collaborator",
            {"author", "reviewer", "workspace_admin", "organization_admin"},
        )
        project = db.query(Project).filter_by(id=project_id, workspace_id=ctx.workspace_id).first()
        if not project:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The project was not found.", 404)
        thread = (
            db.query(AgentThread)
            .filter_by(project_id=project.id, workspace_id=ctx.workspace_id)
            .first()
        )
        if not thread:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE", "The project collaborator thread is unavailable.", 503
            )
        run = start_run(
            db,
            ctx,
            project,
            thread,
            body.text,
            idempotency_key or f"message:{project.id}:{body.text}",
            request.app.state.settings,
        )
        return run

    @app.get("/v1/threads/{thread_id}/events", response_model=list[EventOut])
    def thread_events(
        thread_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        thread = (
            db.query(AgentThread).filter_by(id=thread_id, workspace_id=ctx.workspace_id).first()
        )
        if not thread:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The thread was not found.", 404)
        query = db.query(PublicEvent).filter_by(thread_id=thread.id, workspace_id=ctx.workspace_id)
        if last_event_id:
            previous = db.get(PublicEvent, last_event_id)
            if previous and previous.thread_id == thread.id and previous.workspace_id == ctx.workspace_id:
                query = query.filter(PublicEvent.seq > previous.seq)
        events = query.order_by(PublicEvent.seq).all()
        return [
            {
                "event_id": event.id,
                "seq": event.seq,
                "schema_version": event.schema_version,
                "type": event.event_type,
                "project_id": event.project_id,
                "run_id": event.run_id,
                "thread_id": event.thread_id,
                "occurred_at": event.created_at,
                "payload": event.payload,
            }
            for event in events
        ]

    @app.get("/v1/threads/{thread_id}/events/stream")
    def thread_events_stream(
        thread_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        thread = (
            db.query(AgentThread).filter_by(id=thread_id, workspace_id=ctx.workspace_id).first()
        )
        if not thread:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The thread was not found.", 404)
        query = db.query(PublicEvent).filter_by(thread_id=thread.id, workspace_id=ctx.workspace_id)
        if last_event_id:
            previous = db.get(PublicEvent, last_event_id)
            if previous and previous.thread_id == thread.id and previous.workspace_id == ctx.workspace_id:
                query = query.filter(PublicEvent.seq > previous.seq)
        events = query.order_by(PublicEvent.seq).all()

        def stream():
            for event in events:
                payload = {
                    "event_id": event.id,
                    "seq": event.seq,
                    "schema_version": event.schema_version,
                    "type": event.event_type,
                    "project_id": event.project_id,
                    "run_id": event.run_id,
                    "thread_id": event.thread_id,
                    "occurred_at": event.created_at.isoformat(),
                    "payload": event.payload,
                }
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/runs/{run_id}", response_model=RunOut)
    def run_get(run_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)):
        run = db.query(AgentRun).filter_by(id=run_id, workspace_id=ctx.workspace_id).first()
        if not run:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The run was not found.", 404)
        return run

    @app.post("/v1/runs/{run_id}/cancel", response_model=RunOut)
    def run_cancel(
        run_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        run = db.query(AgentRun).filter_by(id=run_id, workspace_id=ctx.workspace_id).first()
        if not run:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The run was not found.", 404)
        if run.status in {"queued", "running", "waiting_for_user", "waiting_for_approval"}:
            run.cancel_requested = True
            run.status = "cancelled"
            db.commit()
        return run

    @app.post("/v1/delegated-tasks/{task_id}/retry")
    def delegated_task_retry(
        task_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        task = retry_delegated_task(db, ctx, task_id)
        return {
            "id": task.id,
            "project_id": task.project_id,
            "parent_run_id": task.parent_run_id,
            "task_type": task.task_type,
            "status": task.status,
            "attempts": task.result_refs.get("attempts", 0),
            "error_code": task.error_code,
        }

    @app.post("/v1/runs/{run_id}/delegated-tasks/reconcile")
    def delegated_tasks_reconcile(
        run_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return reconcile_delegated_tasks(db, ctx, run_id)

    @app.post("/v1/runs/{run_id}/resume", response_model=RunOut, status_code=202)
    def run_resume(
        run_id: str,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        run = db.query(AgentRun).filter_by(id=run_id, workspace_id=ctx.workspace_id).first()
        if not run:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The run was not found.", 404)
        if run.status not in {"failed", "cancelled", "waiting_for_user", "waiting_for_approval"}:
            raise GroundloomError("INVALID_STATE", "This run cannot be resumed.", 409)
        queue_for_worker = bool(
            (
                request.app.state.settings.env in {"staging", "production"}
                and request.app.state.settings.model_provider != "local"
            )
            or not request.app.state.settings.agent_inline_local
        )
        run.status = "queued" if queue_for_worker else "running"
        run.cancel_requested = False
        db.commit()
        if not queue_for_worker:
            execute_agent_turn(db, ctx, run, request.app.state.settings)
        return run

    @app.get("/v1/runs/{run_id}/approvals", response_model=list[ApprovalOut])
    def run_approvals(
        run_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        run = db.query(AgentRun).filter_by(id=run_id, workspace_id=ctx.workspace_id).first()
        if not run:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The run was not found.", 404)
        return list_run_approvals(db, ctx, run_id)

    @app.post("/v1/approvals/{approval_id}/resolve", response_model=ApprovalOut)
    def approval_resolve(
        approval_id: str,
        body: ApprovalDecision,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        key = body.idempotency_key or idempotency_key
        if key:
            existing = db.query(IdempotencyRecord).filter_by(workspace_id=ctx.workspace_id, key=key).first()
            if existing:
                if existing.operation != "approval.resolve":
                    raise GroundloomError(
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was used for another operation.",
                        409,
                    )
                return existing.response_json
        result = resolve_approval(
            db,
            ctx,
            approval_id,
            body.decision,
            body.reason,
            request.app.state.settings,
        )
        result = remember_idempotency(db, ctx, key, "approval.resolve", result)
        db.commit()
        return result

    @app.get("/v1/sources", response_model=list[SourceOut])
    def sources_get(db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)):
        return list_sources(db, ctx)

    @app.post("/v1/sources/uploads", response_model=SourceOut, status_code=201)
    def sources_upload(
        body: UploadFinalize,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        source = upload_source(db, ctx, request.app.state.settings, body)
        return next(item for item in list_sources(db, ctx) if item["id"] == source.id)

    @app.post("/v1/sources/{source_id}/versions", response_model=SourceOut, status_code=201)
    def source_revision(
        source_id: str,
        body: UploadFinalize,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        source = upload_source(
            db,
            ctx,
            request.app.state.settings,
            body.model_copy(update={"source_id": source_id}),
        )
        return next(item for item in list_sources(db, ctx) if item["id"] == source.id)

    @app.post("/v1/sources/uploads/multipart", response_model=SourceOut, status_code=201)
    async def sources_upload_multipart(
        name: str,
        request: Request,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        import base64

        raw = await file.read()
        body = UploadFinalize(
            name=name,
            filename=file.filename or "source.txt",
            content_base64=base64.b64encode(raw).decode(),
            mime_type=file.content_type or "application/octet-stream",
        )
        source = upload_source(db, ctx, request.app.state.settings, body)
        return next(item for item in list_sources(db, ctx) if item["id"] == source.id)

    @app.get("/v1/sources/{source_id}", response_model=SourceOut)
    def source_get(
        source_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        item = next((item for item in list_sources(db, ctx) if item["id"] == source_id), None)
        if not item:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The source was not found.", 404)
        return item

    @app.get("/v1/source-versions/{version_id}/passages/{passage_id}")
    def passage_get(
        version_id: str,
        passage_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return read_passage(db, ctx, version_id, passage_id)

    @app.post(
        "/v1/source-versions/{version_id}/index-rebuilds",
        response_model=IndexRebuildOut,
        status_code=202,
    )
    def source_index_rebuild(
        version_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return index_rebuild_dto(request_index_rebuild(db, ctx, version_id))

    @app.get("/v1/index-rebuilds/{job_id}", response_model=IndexRebuildOut)
    def index_rebuild_get(
        job_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        job = db.query(IndexRebuildJob).filter_by(id=job_id, workspace_id=ctx.workspace_id).first()
        if not job:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The index rebuild was not found.", 404)
        return index_rebuild_dto(job)

    @app.get("/v1/projects/{project_id}/sources/search", response_model=EvidenceBundle)
    def source_search(
        project_id: str,
        q: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return search_evidence(db, ctx, project_id, q)

    @app.get("/v1/skills")
    def skills_get(db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)):
        return list_skills(db, ctx)

    @app.get("/v1/memory")
    def memory_get(db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)):
        return read_memory(db, ctx)

    @app.post("/v1/memory")
    def memory_write(
        body: MemoryWrite, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        return write_memory(db, ctx, body)

    @app.post("/v1/skills", response_model=SkillVersionOut, status_code=201)
    def skills_create(
        body: SkillCreate, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        version = create_skill(db, ctx, body)
        skill = db.get(Skill, version.skill_id)
        if skill is None:
            raise GroundloomError("INTERNAL_ERROR", "The skill identity is missing.", 500)
        return {
            "id": version.id,
            "skill_id": version.skill_id,
            "version_no": version.version_no,
            "status": version.status,
            "name": skill.name,
            "slug": skill.slug,
            "description": version.description,
            "content_hash": version.content_hash,
            "scope": skill.scope,
        }

    @app.post("/v1/skills/ai-drafts", response_model=SkillVersionOut, status_code=201)
    def skill_ai_draft(
        body: SkillAuthorDraftCreate,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        version = author_skill_draft(db, ctx, body, request.app.state.settings)
        skill = db.get(Skill, version.skill_id)
        if skill is None:
            raise GroundloomError("INTERNAL_ERROR", "The skill identity is missing.", 500)
        return {
            "id": version.id,
            "skill_id": version.skill_id,
            "version_no": version.version_no,
            "status": version.status,
            "name": skill.name,
            "slug": skill.slug,
            "description": version.description,
            "content_hash": version.content_hash,
            "scope": skill.scope,
        }

    @app.post("/v1/skill-versions/{version_id}/validate", response_model=SkillVersionOut)
    def skill_validate(
        version_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        version = validate_skill(db, ctx, version_id)
        skill = db.get(Skill, version.skill_id)
        if skill is None:
            raise GroundloomError("INTERNAL_ERROR", "The skill identity is missing.", 500)
        return {
            "id": version.id,
            "skill_id": version.skill_id,
            "version_no": version.version_no,
            "status": version.status,
            "name": skill.name,
            "slug": skill.slug,
            "description": version.description,
            "content_hash": version.content_hash,
            "scope": skill.scope,
        }

    @app.post("/v1/skill-versions/{version_id}/publish", response_model=SkillVersionOut)
    def skill_publish(
        version_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        version = publish_skill(db, ctx, version_id)
        skill = db.get(Skill, version.skill_id)
        if skill is None:
            raise GroundloomError("INTERNAL_ERROR", "The skill identity is missing.", 500)
        return {
            "id": version.id,
            "skill_id": version.skill_id,
            "version_no": version.version_no,
            "status": version.status,
            "name": skill.name,
            "slug": skill.slug,
            "description": version.description,
            "content_hash": version.content_hash,
            "scope": skill.scope,
        }

    @app.get("/v1/projects/{project_id}/content")
    def project_content(
        project_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        version, blocks = content_blocks(db, ctx, project_id)
        return {
            "version": {
                "id": version.id,
                "version_no": version.version_no,
                "status": version.status,
                "provenance": version.provenance_json,
            },
            "blocks": [
                {
                    "id": b.id,
                    "type": b.block_type,
                    "order": b.order_no,
                    "payload": b.payload,
                    "citations": b.citations,
                }
                for b in blocks
            ],
        }

    @app.get("/v1/projects/{project_id}/outline")
    def project_outline(
        project_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        project = db.query(Project).filter_by(id=project_id, workspace_id=ctx.workspace_id).first()
        if not project:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The project was not found.", 404)
        outline = (
            db.get(OutlineVersion, project.current_outline_version_id)
            if project.current_outline_version_id
            else None
        )
        return (
            {
                "id": outline.id,
                "version_no": outline.version_no,
                "status": outline.status,
                "items": outline.outline_json,
                "provenance": outline.provenance_json,
            }
            if outline
            else {"id": None, "version_no": 0, "status": "empty", "items": [], "provenance": {}}
        )

    @app.post("/v1/projects/{project_id}/outlines/{outline_id}/accept")
    def outline_accept(
        project_id: str,
        outline_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return accept_outline(db, ctx, outline_id)

    @app.get("/v1/projects/{project_id}/patches", response_model=list[PatchOut])
    def patches_get(
        project_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        if not db.query(Project).filter_by(id=project_id, workspace_id=ctx.workspace_id).first():
            raise GroundloomError("RESOURCE_NOT_FOUND", "The project was not found.", 404)
        return [
            patch_out(p)
            for p in db.query(Patch)
            .filter_by(project_id=project_id, workspace_id=ctx.workspace_id)
            .order_by(Patch.created_at.desc())
            .all()
        ]

    @app.post("/v1/projects/{project_id}/patches", response_model=PatchOut, status_code=201)
    def patches_create(
        project_id: str,
        body: PatchCreate,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return patch_out(create_patch(db, ctx, project_id, body))

    @app.post("/v1/patches/{patch_id}/accept", response_model=PatchOut)
    def patch_accept(
        patch_id: str,
        body: DecisionIn,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        patch, _ = accept_patch(db, ctx, patch_id, body)
        return patch_out(patch)

    @app.post("/v1/patches/{patch_id}/reject", response_model=PatchOut)
    def patch_reject(
        patch_id: str,
        body: DecisionIn,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return patch_out(reject_patch(db, ctx, patch_id, body.reason))

    @app.post("/v1/projects/{project_id}/validate", response_model=ValidationOut)
    def content_validate(
        project_id: str, db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        return validation_dto(db, validate_content(db, ctx, project_id))

    @app.post("/v1/exports", response_model=ExportOut, status_code=202)
    def exports_create(
        body: ExportCreate,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        job = export_content(db, ctx, request.app.state.settings, body)
        return export_dto(job, request)

    @app.post(
        "/v1/projects/{project_id}/deletion",
        response_model=DeletionRequestOut,
        status_code=202,
    )
    def project_deletion_request(
        project_id: str,
        body: DeletionRequestCreate,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return deletion_dto(request_project_deletion(db, ctx, project_id, body.idempotency_key))

    @app.get("/v1/workspace/retention-policy", response_model=RetentionPolicyOut)
    def retention_policy_get(
        db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        return get_retention_policy(db, ctx)

    @app.put("/v1/workspace/retention-policy", response_model=RetentionPolicyOut)
    def retention_policy_put(
        body: RetentionPolicyUpdate,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        return update_retention_policy(db, ctx, body)

    @app.get("/v1/workspace/preferences", response_model=WorkspacePreferencesOut)
    def workspace_preferences_get(
        db: Session = Depends(get_db), ctx: RuntimeContext = Depends(get_ctx)
    ):
        return get_workspace_preferences(db, ctx)

    @app.put("/v1/workspace/preferences", response_model=WorkspacePreferencesOut)
    def workspace_preferences_put(
        body: WorkspacePreferencesUpdate,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if idempotency_key:
            existing = db.query(IdempotencyRecord).filter_by(workspace_id=ctx.workspace_id, key=idempotency_key).first()
            if existing:
                if existing.operation != "workspace.preferences.update":
                    raise GroundloomError(
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was used for another operation.",
                        409,
                    )
                return existing.response_json
        result = update_workspace_preferences(db, ctx, body)
        result = remember_idempotency(db, ctx, idempotency_key, "workspace.preferences.update", result)
        db.commit()
        return result

    @app.get("/v1/deletions/{deletion_id}", response_model=DeletionRequestOut)
    def deletion_get(
        deletion_id: str,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        deletion = db.query(DeletionRequest).filter_by(id=deletion_id, workspace_id=ctx.workspace_id).first()
        if not deletion:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The deletion request was not found.", 404)
        return deletion_dto(deletion)

    @app.get("/v1/exports/{export_id}", response_model=ExportOut)
    def export_get(
        export_id: str,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        job = db.query(ExportJob).filter_by(id=export_id, workspace_id=ctx.workspace_id).first()
        if not job:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The export was not found.", 404)
        return export_dto(job, request)

    @app.get("/v1/exports/{export_id}/download")
    def export_download(
        export_id: str,
        request: Request,
        db: Session = Depends(get_db),
        ctx: RuntimeContext = Depends(get_ctx),
    ):
        job = db.query(ExportJob).filter_by(id=export_id, workspace_id=ctx.workspace_id).first()
        if not job or job.status != "completed" or not job.object_key:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The artifact was not found.", 404)
        try:
            data = request.app.state.object_store.get_bytes(job.object_key)
        except GroundloomError as exc:
            if exc.status_code == 404:
                raise GroundloomError(
                    "DEPENDENCY_UNAVAILABLE",
                    "The artifact is temporarily unavailable.",
                    503,
                    retryable=True,
                ) from exc
            raise
        if not data:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The artifact is temporarily unavailable.",
                503,
                retryable=True,
            )
        media_type = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html",
            "md": "text/markdown",
        }.get(job.format, "application/octet-stream")
        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{job.id}.{job.format}"'},
        )

    return app


def export_dto(job: ExportJob, request: Request) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "content_version_id": job.content_version_id,
        "format": job.format,
        "status": job.status,
        "object_key": job.object_key,
        "download_url": f"{request.app.state.settings.public_base_url}/v1/exports/{job.id}/download"
        if job.status == "completed"
        else None,
        "expires_at": job.expires_at,
        "error_code": job.error_code,
    }


def deletion_dto(deletion: DeletionRequest) -> dict:
    return {
        "id": deletion.id,
        "scope_type": deletion.scope_type,
        "resource_id": deletion.resource_id,
        "status": deletion.status,
        "attempts": deletion.attempts,
        "step_status": deletion.step_status,
        "error_code": deletion.error_code,
        "completed_at": deletion.completed_at,
    }


def index_rebuild_dto(job: IndexRebuildJob) -> dict:
    return {
        "id": job.id,
        "source_version_id": job.source_version_id,
        "status": job.status,
        "attempts": job.attempts,
        "error_code": job.error_code,
    }


app = create_app()
