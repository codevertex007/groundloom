from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: str
    object_store: str
    model_provider: str
    version: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_type: str = Field(default="knowledge_brief", min_length=1, max_length=80)
    brief: str = Field(min_length=1, max_length=20_000)
    source_version_ids: list[str] = Field(default_factory=list, max_length=100)
    skill_version_ids: list[str] = Field(default_factory=list, max_length=50)
    defaults: dict[str, Any] = Field(default_factory=dict)


class ProjectOut(ProductModel):
    id: str
    name: str
    project_type: str
    brief: str
    status: str
    current_config_version_id: str | None = None
    current_outline_version_id: str | None = None
    current_content_version_id: str | None = None
    current_run_id: str | None = None
    source_count: int = 0
    section_count: int = 0
    latest_run_status: str | None = None
    updated_at: datetime


class ProjectDetail(ProjectOut):
    config: dict[str, Any]
    thread_id: str | None = None
    todos: list[dict[str, Any]] = Field(default_factory=list)


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class RunOut(ProductModel):
    id: str
    project_id: str
    thread_id: str
    status: str
    request_text: str
    error_code: str | None = None
    created_at: datetime


class EventOut(ProductModel):
    event_id: str
    seq: int
    schema_version: int
    type: str
    project_id: str
    run_id: str
    thread_id: str
    occurred_at: datetime
    payload: dict[str, Any]


class SourceOut(ProductModel):
    id: str
    name: str
    source_type: str
    current_version_id: str | None
    latest_status: str | None = None
    versions: list[dict[str, Any]] = Field(default_factory=list)


class UploadFinalize(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)
    mime_type: str = "text/plain"
    source_id: str | None = None


class PassageOut(BaseModel):
    passage_id: str
    source_id: str
    source_version_id: str
    source_name: str
    page: int | None
    section_path: str
    block_id: str
    offsets: dict[str, int]
    text: str
    score: float


class EvidenceBundle(BaseModel):
    query: str
    retrieval_version: str
    passages: list[PassageOut]
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class SkillCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,119}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    content: str = Field(min_length=1, max_length=100_000)
    scope: Literal["workspace", "organization"] = "workspace"


class SkillAuthorDraftCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=5000)
    suggested_slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,119}$")
    suggested_name: str | None = Field(default=None, min_length=1, max_length=200)
    scope: Literal["workspace", "organization"] = "workspace"


class SkillVersionOut(ProductModel):
    id: str
    skill_id: str
    version_no: int
    status: str
    name: str
    slug: str
    description: str
    content_hash: str
    scope: str


class TodoIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    status: Literal[
        "pending", "in_progress", "blocked", "waiting_for_user", "completed", "cancelled", "failed"
    ] = "pending"


class OutlineProposalIn(BaseModel):
    items: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    idempotency_key: str | None = None


class PatchOperation(BaseModel):
    op: Literal["insert_after", "replace_block", "delete_block", "move_block", "replace_citations"]
    block_id: str | None = None
    after_block_id: str | None = None
    payload: dict[str, Any] | None = None
    citations: list[dict[str, Any]] | None = None


class PatchCreate(BaseModel):
    base_content_version_id: str
    operations: list[PatchOperation] = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    idempotency_key: str | None = None


class PatchOut(ProductModel):
    id: str
    project_id: str
    base_content_version_id: str
    status: str
    operations: list[dict[str, Any]]
    summary: str
    validation: dict[str, Any]
    decision_reason: str | None = None


class DecisionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    expected_current_version_id: str
    idempotency_key: str | None = None


class ValidationOut(BaseModel):
    id: str
    content_version_id: str
    status: str
    summary: dict[str, Any]
    findings: list[dict[str, Any]]


class ExportCreate(BaseModel):
    project_id: str
    content_version_id: str
    format: Literal["pdf", "docx", "html", "md"] = "pdf"
    idempotency_key: str | None = None


class ExportOut(ProductModel):
    id: str
    project_id: str
    content_version_id: str
    format: str
    status: str
    object_key: str | None = None
    download_url: str | None = None
    expires_at: datetime | None = None
    error_code: str | None = None


class DeletionRequestCreate(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=180)


class DeletionRequestOut(ProductModel):
    id: str
    scope_type: str
    resource_id: str
    status: str
    attempts: int
    step_status: dict[str, Any]
    error_code: str | None = None
    completed_at: datetime | None = None


class RetentionPolicyUpdate(BaseModel):
    sources_days: int = Field(default=365, ge=1, le=36_500)
    projects_days: int = Field(default=365, ge=1, le=36_500)
    agent_data_days: int = Field(default=90, ge=1, le=36_500)
    exports_days: int = Field(default=7, ge=1, le=36_500)
    audit_days: int = Field(default=2555, ge=1, le=36_500)
    legal_hold: bool = False


class RetentionPolicyOut(ProductModel):
    workspace_id: str
    sources_days: int
    projects_days: int
    agent_data_days: int
    exports_days: int
    audit_days: int
    legal_hold: bool


class IndexRebuildOut(ProductModel):
    id: str
    source_version_id: str
    status: str
    attempts: int
    error_code: str | None = None


class MemoryWrite(BaseModel):
    namespace: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,159}$")
    value: dict[str, Any] = Field(default_factory=dict)
