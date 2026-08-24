from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..context import RuntimeContext
from ..schemas import PatchCreate
from ..services import content_blocks, create_patch, project_detail, search_evidence


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    name: str
    mode: str
    max_result_items: int
    handler: Callable[..., Any]


def get_project_snapshot(db: Session, ctx: RuntimeContext, project_id: str) -> dict:
    return project_detail(db, ctx, project_id)


def search_source_passages(db: Session, ctx: RuntimeContext, project_id: str, query: str):
    return search_evidence(db, ctx, project_id, query, limit=8)


def read_content_blocks(db: Session, ctx: RuntimeContext, project_id: str, version_id: str | None = None) -> dict:
    version, blocks = content_blocks(db, ctx, project_id, version_id)
    return {"version_id": version.id, "version_no": version.version_no, "blocks": [{"id": b.id, "type": b.block_type, "payload": b.payload, "citations": b.citations} for b in blocks]}


def propose_block_patch(db: Session, ctx: RuntimeContext, project_id: str, request: PatchCreate) -> str:
    return create_patch(db, ctx, project_id, request).id


TOOL_REGISTRY = {
    "TOOL-PROJ-001": ToolSpec("TOOL-PROJ-001", "get_project_snapshot", "read", 1, get_project_snapshot),
    "TOOL-RET-001": ToolSpec("TOOL-RET-001", "search_source_passages", "read", 8, search_source_passages),
    "TOOL-CONT-001": ToolSpec("TOOL-CONT-001", "read_content_blocks", "read", 100, read_content_blocks),
    "TOOL-CONT-003": ToolSpec("TOOL-CONT-003", "propose_block_patch", "proposal", 1, propose_block_patch),
}
