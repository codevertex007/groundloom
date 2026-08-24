from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


JsonType = JSON().with_variant(JSONB, "postgresql")


class TimeStamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Workspace(TimeStamped, Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    policy_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class User(TimeStamped, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class Membership(TimeStamped, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="author")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Project(TimeStamped, Base):
    __tablename__ = "projects"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_type: Mapped[str] = mapped_column(String(80), nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    current_config_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    current_outline_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    current_content_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    current_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class ProjectConfigVersion(TimeStamped, Base):
    __tablename__ = "project_config_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_no", name="uq_project_config_version"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version_ids: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    skill_version_ids: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    defaults_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)


class Source(TimeStamped, Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class SourceVersion(TimeStamped, Base):
    __tablename__ = "source_versions"
    __table_args__ = (UniqueConstraint("source_id", "version_no", name="uq_source_version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="uploaded", index=True)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class IngestionJob(TimeStamped, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (UniqueConstraint("workspace_id", "source_version_id", name="uq_ingestion_version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class SourceBlock(TimeStamped, Base):
    __tablename__ = "source_blocks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id"), nullable=False, index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    block_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    security_signals: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)


class SourceChunk(TimeStamped, Base):
    __tablename__ = "source_chunks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("source_versions.id"), nullable=False, index=True
    )
    source_block_id: Mapped[str] = mapped_column(
        ForeignKey("source_blocks.id"), nullable=False, index=True
    )
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_terms: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    embedding_json: Mapped[list | None] = mapped_column(JsonType, nullable=True)


class Skill(TimeStamped, Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(30), nullable=False, default="workspace")
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class SkillVersion(TimeStamped, Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version_no", name="uq_skill_version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    package_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)


class AgentThread(TimeStamped, Base):
    __tablename__ = "agent_threads"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, unique=True)
    thread_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    agent_definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class AgentRun(TimeStamped, Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("agent_threads.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    pinned_config_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PublicEvent(TimeStamped, Base):
    __tablename__ = "public_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_public_event_run_seq"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class Todo(TimeStamped, Base):
    __tablename__ = "todos"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class OutlineVersion(TimeStamped, Base):
    __tablename__ = "outline_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_no", name="uq_outline_version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    outline_json: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ContentVersion(TimeStamped, Base):
    __tablename__ = "content_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_no", name="uq_content_version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="accepted")
    parent_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provenance_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ContentBlock(TimeStamped, Base):
    __tablename__ = "content_blocks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    content_version_id: Mapped[str] = mapped_column(
        ForeignKey("content_versions.id"), nullable=False, index=True
    )
    block_type: Mapped[str] = mapped_column(String(40), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    citations: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)


class Patch(TimeStamped, Base):
    __tablename__ = "patches"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    base_content_version_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    operations: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    validation_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ValidationRun(TimeStamped, Base):
    __tablename__ = "validation_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    content_version_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class ValidationFinding(TimeStamped, Base):
    __tablename__ = "validation_findings"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    validation_run_id: Mapped[str] = mapped_column(
        ForeignKey("validation_runs.id"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    block_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)


class ExportJob(TimeStamped, Base):
    __tablename__ = "export_jobs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    content_version_id: Mapped[str] = mapped_column(String(80), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetentionPolicy(TimeStamped, Base):
    __tablename__ = "retention_policies"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    sources_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)
    projects_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)
    agent_data_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    exports_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    audit_days: Mapped[int] = mapped_column(Integer, default=2555, nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DeletionRequest(TimeStamped, Base):
    __tablename__ = "deletion_requests"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step_status: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(TimeStamped, Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)


class IdempotencyRecord(TimeStamped, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_idempotency_workspace_key"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(180), nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    response_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class OutboxMessage(TimeStamped, Base):
    __tablename__ = "outbox_messages"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MemoryItem(TimeStamped, Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", "namespace", "key", name="uq_memory_scope_key"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    value_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="approved", nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


class DelegatedTask(TimeStamped, Base):
    __tablename__ = "delegated_tasks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    parent_run_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    input_refs: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    result_refs: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
