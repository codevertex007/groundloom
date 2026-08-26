"""Source ingestion, derived-index lifecycle, and evidence passage services."""

import base64
import hashlib
import re
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import Settings
from ..context import RuntimeContext
from ..db import set_tenant_context
from ..errors import GroundloomError
from ..ids import new_id
from ..integrations.ai.indexing import replace_source_version_index
from ..integrations.documents import parse_source
from ..models import (
    IndexRebuildJob,
    IngestionJob,
    Source,
    SourceBlock,
    SourceVersion,
    utcnow,
)
from ..object_store import build_object_store
from ..schemas import UploadFinalize
from ..source_safety import build_source_scanner
from .audit import audit
from .events import outbox
from .operations import touch_worker_heartbeat


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
    build_object_store(settings).put_bytes(object_key, raw)
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
    ingestion_job = IngestionJob(
        id=new_id("ing"),
        workspace_id=ctx.workspace_id,
        source_version_id=version.id,
        status="queued",
        stage="queued",
    )
    db.add(ingestion_job)
    try:
        process_ingestion_job(db, ctx, settings, ingestion_job, raw=raw)
    except GroundloomError:
        db.commit()
        raise
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


def process_ingestion_job(
    db: Session,
    ctx: RuntimeContext,
    settings: Settings,
    job: IngestionJob,
    *,
    raw: bytes | None = None,
) -> SourceVersion:
    """Run the idempotent source state machine for one leased job.

    The API uses this synchronously for the local adapter. The worker entrypoint
    uses the same function after claiming a queued/expired job, so parsing and
    indexing cannot drift between local and deployment execution.
    """
    if job.workspace_id != ctx.workspace_id:
        raise GroundloomError("FORBIDDEN", "The ingestion job is outside the workspace scope.", 403)
    version = (
        db.query(SourceVersion)
        .filter_by(id=job.source_version_id, workspace_id=ctx.workspace_id)
        .first()
    )
    if not version:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The source version was not found.", 404)
    if version.status == "ready" and job.status == "completed":
        return version
    if raw is None:
        raw = build_object_store(settings).get_bytes(version.object_key)
    if len(raw) > settings.max_upload_bytes:
        version.status = "failed"
        version.failure_code = "SIZE_LIMIT"
        job.status = "failed"
        job.stage = "failed"
        job.error_code = version.failure_code
        job.lease_owner = None
        job.lease_until = None
        append_source_stage(db, ctx, version, "failed")
        raise GroundloomError("INVALID_INPUT", "The source exceeds the configured size limit.", 422)
    extension = Path(version.object_key).suffix.lower().removeprefix(".")
    job.status = "running"
    job.stage = "scanning"
    version.status = "scanning"
    append_source_stage(db, ctx, version, "scanning")
    try:
        build_source_scanner(settings).scan(raw, extension)
    except GroundloomError as exc:
        version.status = "quarantined" if exc.code == "SOURCE_QUARANTINED" else "failed"
        version.failure_code = exc.code
        job.status = "failed"
        job.stage = "failed"
        job.error_code = exc.code
        job.lease_owner = None
        job.lease_until = None
        append_source_stage(db, ctx, version, version.status)
        raise
    try:
        text = parse_source(raw, extension)
    except (KeyError, OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        version.status = "failed"
        version.failure_code = "PARSE_FAILED"
        job.status = "failed"
        job.stage = "failed"
        job.error_code = version.failure_code
        job.lease_owner = None
        job.lease_until = None
        append_source_stage(db, ctx, version, "failed")
        raise GroundloomError(
            "JOB_FAILED", "The source parser rejected this document.", 422
        ) from exc
    if not text.strip() and extension == "pdf":
        version.status = "ocr"
        job.stage = "ocr"
        append_source_stage(db, ctx, version, "ocr")
        try:
            from ..ocr import build_ocr_provider

            text = build_ocr_provider(settings).extract(raw, extension)
        except GroundloomError as exc:
            version.status = "failed"
            version.failure_code = exc.code
            job.status = "failed"
            job.stage = "failed"
            job.error_code = exc.code
            job.lease_owner = None
            job.lease_until = None
            append_source_stage(db, ctx, version, "failed")
            raise
    if not text.strip():
        version.status = "failed"
        version.failure_code = "EMPTY_DOCUMENT"
        job.status = "failed"
        job.stage = "failed"
        job.error_code = version.failure_code
        job.lease_owner = None
        job.lease_until = None
        append_source_stage(db, ctx, version, "failed")
        raise GroundloomError("JOB_FAILED", "The source could not produce readable text.", 422)
    version.status = "normalizing"
    job.stage = "normalizing"
    append_source_stage(db, ctx, version, "normalizing")
    existing = db.query(SourceBlock).filter_by(source_version_id=version.id).count()
    if not existing:
        paragraphs = [
            p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()
        ] or [text.strip()]
        blocks: list[SourceBlock] = []
        for index, paragraph in enumerate(paragraphs):
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
            blocks.append(block)
        replace_source_version_index(db, settings, blocks, clear_existing=False)
    version.status = "indexing"
    job.stage = "indexing"
    append_source_stage(db, ctx, version, "indexing")
    version.status = "ready"
    job.status = "completed"
    job.stage = "ready"
    job.lease_owner = None
    job.lease_until = None
    source = db.query(Source).filter_by(id=version.source_id, workspace_id=ctx.workspace_id).first()
    if source:
        source.current_version_id = version.id
    append_source_stage(db, ctx, version, "ready")
    return version


def claim_ingestion_jobs(
    db: Session, workspace_id: str, worker_id: str, *, limit: int = 10, lease_seconds: int = 300
) -> list[IngestionJob]:
    """Claim queued or expired jobs with a bounded durable lease."""
    now = utcnow()
    rows = (
        db.query(IngestionJob)
        .filter(IngestionJob.workspace_id == workspace_id)
        .filter(
            (IngestionJob.status == "queued")
            | ((IngestionJob.status == "running") & (IngestionJob.lease_until < now))
        )
        .order_by(IngestionJob.created_at)
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


def run_ingestion_worker_once(
    db: Session,
    ctx: RuntimeContext,
    settings: Settings,
    worker_id: str,
    *,
    limit: int = 10,
) -> dict[str, int]:
    set_tenant_context(db, ctx.workspace_id)
    touch_worker_heartbeat(db, worker_id, "ingestion", ctx.workspace_id, details={"limit": limit})
    db.commit()
    claimed = claim_ingestion_jobs(db, ctx.workspace_id, worker_id, limit=limit)
    completed = 0
    failed = 0
    for job in claimed:
        try:
            process_ingestion_job(db, ctx, settings, job)
            audit(db, ctx, "ingestion.job.completed", "ingestion_job", job.id, "Ingestion completed")
            db.commit()
            completed += 1
        except GroundloomError as exc:
            quarantined = exc.code == "SOURCE_QUARANTINED"
            db.rollback()
            failed_job = (
                db.query(IngestionJob)
                .filter_by(id=job.id, workspace_id=ctx.workspace_id)
                .first()
            )
            if failed_job:
                failed_job.status = "failed"
                failed_job.stage = "failed"
                failed_job.error_code = exc.code
                failed_job.lease_owner = None
                failed_job.lease_until = None
                failed_version = (
                    db.query(SourceVersion)
                    .filter_by(
                        id=failed_job.source_version_id,
                        workspace_id=ctx.workspace_id,
                    )
                    .first()
                )
                if failed_version:
                    failed_version.status = "quarantined" if quarantined else "failed"
                    failed_version.failure_code = exc.code
                db.commit()
            failed += 1
    result = {"claimed": len(claimed), "completed": completed, "failed": failed}
    touch_worker_heartbeat(db, worker_id, "ingestion", ctx.workspace_id, details=result)
    db.commit()
    return result


def request_index_rebuild(
    db: Session, ctx: RuntimeContext, source_version_id: str
) -> IndexRebuildJob:
    ctx.require("rebuild source index", {"workspace_admin", "organization_admin"})
    version = (
        db.query(SourceVersion)
        .filter_by(id=source_version_id, workspace_id=ctx.workspace_id)
        .first()
    )
    if not version:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The source version was not found.", 404)
    if version.status != "ready":
        raise GroundloomError("SOURCE_NOT_READY", "Only ready source versions can be rebuilt.", 409)
    existing = (
        db.query(IndexRebuildJob)
        .filter_by(workspace_id=ctx.workspace_id, source_version_id=source_version_id)
        .filter(IndexRebuildJob.status.in_(["queued", "running"]))
        .first()
    )
    if existing:
        return existing
    job = IndexRebuildJob(
        id=new_id("idx"),
        workspace_id=ctx.workspace_id,
        source_version_id=source_version_id,
        status="queued",
    )
    db.add(job)
    audit(db, ctx, "source.index_rebuild.requested", "index_rebuild_job", job.id, "Queued derived index rebuild")
    outbox(
        db,
        ctx.workspace_id,
        "SourceIndexRebuildRequested",
        "index_rebuild_job",
        job.id,
        {"job_id": job.id, "source_version_id": source_version_id},
    )
    db.commit()
    return job


def claim_index_rebuild_jobs(
    db: Session,
    workspace_id: str,
    worker_id: str,
    *,
    limit: int = 10,
    lease_seconds: int = 300,
) -> list[IndexRebuildJob]:
    now = utcnow()
    rows = (
        db.query(IndexRebuildJob)
        .filter(IndexRebuildJob.workspace_id == workspace_id)
        .filter(
            (IndexRebuildJob.status == "queued")
            | ((IndexRebuildJob.status == "running") & (IndexRebuildJob.lease_until < now))
        )
        .order_by(IndexRebuildJob.created_at)
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


def process_index_rebuild_job(
    db: Session,
    ctx: RuntimeContext,
    job: IndexRebuildJob,
    settings: Settings | None = None,
) -> IndexRebuildJob:
    if job.workspace_id != ctx.workspace_id:
        raise GroundloomError("FORBIDDEN", "The index job is outside the workspace scope.", 403)
    version = (
        db.query(SourceVersion)
        .filter_by(id=job.source_version_id, workspace_id=ctx.workspace_id)
        .first()
    )
    if not version:
        raise GroundloomError("RESOURCE_NOT_FOUND", "The source version was not found.", 404)
    blocks = (
        db.query(SourceBlock)
        .filter_by(source_version_id=version.id, workspace_id=ctx.workspace_id)
        .order_by(SourceBlock.block_no)
        .all()
    )
    replace_source_version_index(db, settings or Settings(), blocks, clear_existing=True)
    job.status = "completed"
    job.error_code = None
    job.lease_owner = None
    job.lease_until = None
    audit(db, ctx, "source.index_rebuild.completed", "index_rebuild_job", job.id, "Rebuilt derived lexical index")
    outbox(
        db,
        ctx.workspace_id,
        "SourceIndexRebuildCompleted",
        "index_rebuild_job",
        job.id,
        {"job_id": job.id, "source_version_id": version.id, "chunk_count": len(blocks)},
    )
    db.commit()
    return job


def run_index_rebuild_worker_once(
    db: Session,
    ctx: RuntimeContext,
    worker_id: str,
    *,
    limit: int = 10,
    settings: Settings | None = None,
) -> dict[str, int]:
    set_tenant_context(db, ctx.workspace_id)
    touch_worker_heartbeat(db, worker_id, "index", ctx.workspace_id, details={"limit": limit})
    db.commit()
    claimed = claim_index_rebuild_jobs(db, ctx.workspace_id, worker_id, limit=limit)
    completed = failed = 0
    for job in claimed:
        try:
            process_index_rebuild_job(db, ctx, job, settings)
            completed += 1
        except Exception as exc:
            db.rollback()
            failed_job = db.query(IndexRebuildJob).filter_by(id=job.id, workspace_id=ctx.workspace_id).first()
            if failed_job:
                failed_job.status = "failed"
                failed_job.error_code = exc.code if isinstance(exc, GroundloomError) else "INDEX_REBUILD_FAILED"
                failed_job.lease_owner = None
                failed_job.lease_until = None
                audit(db, ctx, "source.index_rebuild.failed", "index_rebuild_job", failed_job.id, "Derived index rebuild failed", "failure")
                db.commit()
            failed += 1
    result = {"claimed": len(claimed), "completed": completed, "failed": failed}
    touch_worker_heartbeat(db, worker_id, "index", ctx.workspace_id, details=result)
    db.commit()
    return result


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
