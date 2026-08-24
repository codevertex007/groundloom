import base64
import hashlib
import re
import zipfile
from datetime import timedelta
from html import unescape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import Settings
from .context import RuntimeContext
from .errors import GroundloomError
from .ids import new_id
from .models import (
    AgentRun,
    AgentThread,
    AuditEvent,
    ContentBlock,
    ContentVersion,
    DelegatedTask,
    ExportJob,
    IdempotencyRecord,
    Membership,
    MemoryItem,
    OutboxMessage,
    OutlineVersion,
    Patch,
    Project,
    ProjectConfigVersion,
    PublicEvent,
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
    utcnow,
)
from .schemas import (
    DecisionIn,
    EvidenceBundle,
    ExportCreate,
    MemoryWrite,
    PassageOut,
    PatchCreate,
    ProjectCreate,
    SkillCreate,
    UploadFinalize,
)


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


def remember_idempotency(
    db: Session, ctx: RuntimeContext, key: str | None, operation: str, response: dict
) -> dict:
    if not key:
        return response
    existing = db.query(IdempotencyRecord).filter_by(workspace_id=ctx.workspace_id, key=key).first()
    if existing:
        if existing.operation != operation:
            raise GroundloomError(
                "IDEMPOTENCY_CONFLICT", "The idempotency key was used for another operation.", 409
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


def seed_local(db: Session, settings: Settings) -> None:
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


def create_project(db: Session, ctx: RuntimeContext, body: ProjectCreate) -> Project:
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
        defaults_json=body.defaults,
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
    config = (
        db.get(ProjectConfigVersion, project.current_config_version_id)
        if project.current_config_version_id
        else None
    )
    run = AgentRun(
        id=new_id("run"),
        workspace_id=ctx.workspace_id,
        project_id=project.id,
        thread_id=thread.id,
        status="running",
        request_text=request_text,
        idempotency_key=idempotency_key,
        pinned_config_json={
            "config_version_id": config.id if config else None,
            "source_version_ids": config.source_version_ids if config else [],
            "skill_version_ids": config.skill_version_ids if config else [],
            "prompt_version": "groundloom.prompt.v1",
            "tool_contract_version": "groundloom.tools.v1",
            "model_profile": "local.deterministic.v1",
            "retrieval_version": "lexical.v1",
            "evaluator_version": "deterministic.v1",
        },
    )
    db.add(run)
    project.current_run_id = run.id
    db.flush()
    append_event(db, ctx, run, "run.started", {"status": "running", "request": request_text[:500]})
    db.commit()
    execute_agent_turn(db, ctx, run)
    completed = db.get(AgentRun, run.id)
    if completed is None:
        raise GroundloomError("INTERNAL_ERROR", "The run disappeared before completion.", 500)
    return completed


def _selected_versions(db: Session, run: AgentRun) -> list[str]:
    return run.pinned_config_json.get("source_version_ids", [])


def search_evidence(
    db: Session, ctx: RuntimeContext, project_id: str, query: str, limit: int = 8
) -> EvidenceBundle:
    project = _project(db, ctx, project_id)
    config = db.get(ProjectConfigVersion, project.current_config_version_id)
    allowed = set(config.source_version_ids if config else [])
    if not allowed:
        return EvidenceBundle(
            query=query,
            retrieval_version="lexical.v1",
            passages=[],
            gaps=["No selected source versions are available."],
        )
    terms = [t.lower() for t in re.findall(r"[\w-]{3,}", query)]
    blocks = (
        db.query(SourceBlock, Source)
        .join(SourceVersion, SourceVersion.id == SourceBlock.source_version_id)
        .join(Source, Source.id == SourceVersion.source_id)
        .filter(
            SourceBlock.workspace_id == ctx.workspace_id, SourceBlock.source_version_id.in_(allowed)
        )
        .all()
    )
    ranked: list[tuple[float, SourceBlock, Source]] = []
    for block, source in blocks:
        text = block.text.lower()
        score = sum(1 for term in terms if term in text) / max(len(terms), 1)
        if score > 0:
            ranked.append((score, block, source))
    ranked.sort(key=lambda item: (-item[0], item[1].block_no))
    passages: list[PassageOut] = []
    for score, block, source in ranked[:limit]:
        passages.append(
            PassageOut(
                passage_id=f"passage_{block.id}",
                source_id=source.id,
                source_version_id=block.source_version_id,
                source_name=source.name,
                page=block.page_no,
                section_path=block.section_path,
                block_id=block.id,
                offsets={"start": 0, "end": len(block.text)},
                text=block.text[:3000],
                score=round(score, 4),
            )
        )
    return EvidenceBundle(
        query=query,
        retrieval_version="lexical.v1",
        passages=passages,
        gaps=[] if passages else ["No selected passage matched the request."],
    )


def execute_agent_turn(db: Session, ctx: RuntimeContext, run: AgentRun) -> None:
    project = _project(db, ctx, run.project_id)
    text = run.request_text.lower()
    if run.cancel_requested:
        run.status = "cancelled"
        append_event(db, ctx, run, "run.cancelled", {"status": "cancelled"})
        db.commit()
        return
    if "initialize" in text or "hello" in text:
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
        audit(db, ctx, "run.completed", "agent_run", run.id, "Initialized primary project thread")
        db.commit()
        return
    add_todo(db, ctx, run, "Understand the request and inspect project state", "completed", 0)
    evidence = search_evidence(db, ctx, project.id, run.request_text, limit=8)
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
        db.commit()
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
    audit(
        db,
        ctx,
        "run.completed",
        "agent_run",
        run.id,
        "Produced adaptive outline and content proposal",
    )
    db.commit()


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


def upload_source(
    db: Session, ctx: RuntimeContext, settings: Settings, body: UploadFinalize
) -> Source:
    ctx.require("upload sources", {"author", "reviewer", "workspace_admin", "organization_admin"})
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except Exception as exc:
        raise GroundloomError("INVALID_INPUT", "content_base64 is invalid.", 422) from exc
    if len(raw) > settings.max_upload_bytes:
        raise GroundloomError("INVALID_INPUT", "The upload exceeds the configured size limit.", 422)
    extension = Path(body.filename).suffix.lower().removeprefix(".")
    if extension not in {"txt", "md", "pdf", "docx"}:
        raise GroundloomError(
            "INVALID_INPUT", "Only PDF, DOCX, TXT, and Markdown sources are supported.", 422
        )
    if body.source_id:
        source = (
            db.query(Source)
            .filter_by(id=body.source_id, workspace_id=ctx.workspace_id)
            .first()
        )
        if not source:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The source was not found.", 404)
        if source.source_type != (extension or "txt"):
            raise GroundloomError(
                "INVALID_INPUT",
                "A source revision must keep the source type of its lineage.",
                422,
            )
    else:
        source = Source(
            id=new_id("src"),
            workspace_id=ctx.workspace_id,
            name=body.name,
            source_type=extension or "txt",
        )
        db.add(source)
        db.flush()
    version_no = (
        db.query(func.max(SourceVersion.version_no)).filter_by(source_id=source.id).scalar() or 0
    ) + 1
    object_key = f"workspaces/{ctx.workspace_id}/sources/{source.id}/versions/{version_no}/original{Path(body.filename).suffix.lower()}"
    settings.object_store_path.joinpath(object_key).parent.mkdir(parents=True, exist_ok=True)
    settings.object_store_path.joinpath(object_key).write_bytes(raw)
    version = SourceVersion(
        id=new_id("sv"),
        workspace_id=ctx.workspace_id,
        source_id=source.id,
        version_no=version_no,
        status="scanning",
        object_key=object_key,
        content_hash=hashlib.sha256(raw).hexdigest(),
        mime_type=body.mime_type,
        size_bytes=len(raw),
    )
    db.add(version)
    db.flush()
    append_source_stage(db, ctx, version, "scanning")
    text = parse_source(raw, extension)
    if not text.strip():
        version.status = "failed"
        version.failure_code = "EMPTY_DOCUMENT"
        append_source_stage(db, ctx, version, "failed")
        db.commit()
        raise GroundloomError("JOB_FAILED", "The source could not produce readable text.", 422)
    version.status = "normalizing"
    append_source_stage(db, ctx, version, "normalizing")
    for index, paragraph in enumerate(
        [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [text.strip()]
    ):
        signals = (
            ["possible_instruction_text"]
            if re.search(r"ignore (previous|all) instructions|system prompt", paragraph, re.I)
            else []
        )
        block = SourceBlock(
            id=new_id("blk"),
            workspace_id=ctx.workspace_id,
            source_version_id=version.id,
            page_no=index + 1 if extension == "pdf" else None,
            section_path="",
            block_no=index,
            text=paragraph[:20_000],
            security_signals=signals,
        )
        db.add(block)
        db.flush()
        terms = sorted(set(re.findall(r"[a-z0-9]{3,}", paragraph.lower())))
        db.add(
            SourceChunk(
                id=new_id("chk"),
                workspace_id=ctx.workspace_id,
                source_version_id=version.id,
                source_block_id=block.id,
                chunk_no=0,
                text=paragraph[:5000],
                token_terms=terms,
            )
        )
    version.status = "indexing"
    append_source_stage(db, ctx, version, "indexing")
    version.status = "ready"
    source.current_version_id = version.id
    append_source_stage(db, ctx, version, "ready")
    audit(
        db,
        ctx,
        "source.version.uploaded",
        "source_version",
        version.id,
        "Stored and indexed source version",
    )
    db.commit()
    return source


def append_source_stage(
    db: Session, ctx: RuntimeContext, version: SourceVersion, status: str
) -> None:
    outbox(
        db,
        ctx.workspace_id,
        "SourceStageChanged",
        "source_version",
        version.id,
        {"source_version_id": version.id, "status": status},
    )


def parse_source(raw: bytes, extension: str) -> str:
    if extension in {"txt", "md"}:
        return raw.decode("utf-8", errors="replace")
    if extension == "docx":
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        return "\n".join(
            "".join(node.itertext()).strip()
            for node in root.iter()
            if node.tag.endswith("}p") and "".join(node.itertext()).strip()
        )
    if extension == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(__import__("io").BytesIO(raw))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
    return ""


def list_sources(db: Session, ctx: RuntimeContext) -> list[dict[str, Any]]:
    rows = (
        db.query(Source)
        .filter_by(workspace_id=ctx.workspace_id)
        .order_by(Source.updated_at.desc())
        .all()
    )
    output = []
    for source in rows:
        versions = (
            db.query(SourceVersion)
            .filter_by(source_id=source.id, workspace_id=ctx.workspace_id)
            .order_by(SourceVersion.version_no.desc())
            .all()
        )
        output.append(
            {
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type,
                "current_version_id": source.current_version_id,
                "latest_status": versions[0].status if versions else None,
                "versions": [
                    {
                        "id": v.id,
                        "version_no": v.version_no,
                        "status": v.status,
                        "size_bytes": v.size_bytes,
                        "created_at": v.created_at,
                    }
                    for v in versions
                ],
            }
        )
    return output


def read_passage(
    db: Session, ctx: RuntimeContext, version_id: str, passage_id: str
) -> dict[str, Any]:
    block_id = passage_id.removeprefix("passage_")
    block = (
        db.query(SourceBlock)
        .filter_by(id=block_id, source_version_id=version_id, workspace_id=ctx.workspace_id)
        .first()
    )
    if not block:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The passage was not found.", 404)
    source_version = db.get(SourceVersion, version_id)
    source = db.get(Source, source_version.source_id) if source_version else None
    if source is None:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The source was not found.", 404)
    return {
        "passage_id": passage_id,
        "source_id": source.id,
        "source_version_id": version_id,
        "source_name": source.name,
        "page": block.page_no,
        "section_path": block.section_path,
        "block_id": block.id,
        "offsets": {"start": 0, "end": len(block.text)},
        "text": block.text,
        "score": 1.0,
    }


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
    db: Session, ctx: RuntimeContext, project_id: str, version_id: str | None = None
) -> ValidationRun:
    ctx.require(
        "validate content",
        {"viewer", "author", "reviewer", "workspace_admin", "organization_admin"},
    )
    version, blocks = content_blocks(db, ctx, project_id, version_id)
    findings: list[dict[str, Any]] = []
    for block in blocks:
        if (
            block.block_type in {"paragraph", "warning", "note"}
            and not block.payload.get("text", "").strip()
        ):
            findings.append(
                {
                    "severity": "error",
                    "category": "structure",
                    "block_id": block.id,
                    "message": "Text block is empty.",
                }
            )
        if block.block_type == "paragraph" and block.payload.get("text") and not block.citations:
            findings.append(
                {
                    "severity": "warning",
                    "category": "citation",
                    "block_id": block.id,
                    "message": "Paragraph has no citation; mark unsupported claims or add evidence.",
                }
            )
    validation = ValidationRun(
        id=new_id("val"),
        workspace_id=ctx.workspace_id,
        project_id=project_id,
        content_version_id=version.id,
        status="failed" if any(f["severity"] == "error" for f in findings) else "passed",
        summary_json={
            "finding_count": len(findings),
            "error_count": sum(1 for f in findings if f["severity"] == "error"),
            "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
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
        "Ran deterministic content validation",
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
    version, blocks = content_blocks(db, ctx, project.id, body.content_version_id)
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
        status="rendering",
        idempotency_key=key,
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(job)
    db.flush()
    settings.object_store_path.joinpath("workspaces", ctx.workspace_id, "exports").mkdir(
        parents=True, exist_ok=True
    )
    rendered = render_content(project.name, blocks, body.format)
    suffix = {"md": "md", "html": "html", "pdf": "pdf", "docx": "docx"}[body.format]
    object_key = f"workspaces/{ctx.workspace_id}/exports/{job.id}.{suffix}"
    settings.object_store_path.joinpath(object_key).parent.mkdir(parents=True, exist_ok=True)
    settings.object_store_path.joinpath(object_key).write_bytes(rendered)
    job.object_key = object_key
    job.status = "completed"
    audit(db, ctx, "export.completed", "export_job", job.id, "Rendered immutable content version")
    outbox(
        db,
        ctx.workspace_id,
        "ExportCompleted",
        "export_job",
        job.id,
        {"export_id": job.id, "content_version_id": version.id, "format": body.format},
    )
    db.commit()
    return job


def render_content(title: str, blocks: list[ContentBlock], format: str) -> bytes:
    lines = [title, "=" * max(len(title), 3)]
    for block in blocks:
        text = block.payload.get("text", block.payload.get("title", ""))
        if block.block_type == "heading":
            lines.extend(["", str(text), "-" * max(len(str(text)), 3)])
        else:
            lines.extend(["", str(text)])
    markdown = "\n".join(lines) + "\n"
    if format == "md":
        return markdown.encode()
    if format == "html":
        body = "".join(
            f"<h1>{unescape(line)}</h1>" if i == 0 else f"<p>{unescape(line)}</p>"
            for i, line in enumerate(lines)
            if line
        )
        return f"<!doctype html><html><head><meta charset='utf-8'><title>{unescape(title)}</title></head><body>{body}</body></html>".encode()
    if format == "docx":
        return minimal_docx(lines)
    return minimal_pdf(lines)


def minimal_docx(lines: list[str]) -> bytes:
    import io

    document = "".join(
        f"<w:p><w:r><w:t xml:space='preserve'>{unescape(line)}</w:t></w:r></w:p>" for line in lines
    )
    files = {
        "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>",
        "_rels/.rels": "<?xml version='1.0'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>",
        "word/document.xml": f"<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>{document}</w:body></w:document>",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def minimal_pdf(lines: list[str]) -> bytes:
    content = (
        "BT /F1 11 Tf 50 760 Td "
        + " ".join(
            f"({line.replace('(', '[').replace(')', ']')}) Tj 0 -16 Td" for line in lines[:45]
        )
        + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode())
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    result.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return bytes(result)
