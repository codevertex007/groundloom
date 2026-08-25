"""Typed content read, validation, and proposal tools."""

from collections.abc import Callable
from typing import Any

from ...schemas import PatchCreate, PatchOperation
from ...services import (
    content_blocks,
    create_patch,
    validate_content,
    validation_dto,
)
from ..contracts import ToolContext


def build_content_tools(scope: ToolContext) -> dict[str, Callable[..., Any]]:
    def validate_current_content() -> dict[str, Any]:
        """Run deterministic validation without mutating canonical content."""

        validation = validate_content(scope.db, scope.runtime_context, scope.project_id)
        return validation_dto(scope.db, validation)

    def read_current_content() -> dict[str, Any]:
        """Read the current typed content version and its blocks."""

        version, blocks = content_blocks(scope.db, scope.runtime_context, scope.project_id)
        return {
            "version_id": version.id,
            "version_no": version.version_no,
            "blocks": [
                {
                    "id": block.id,
                    "type": block.block_type,
                    "payload": block.payload,
                    "citations": block.citations,
                }
                for block in blocks
            ],
        }

    def propose_text_patch(
        summary: str, text: str, citations: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Create a validated reviewable patch; never commit canonical content."""

        version, blocks = content_blocks(scope.db, scope.runtime_context, scope.project_id)
        operation = PatchOperation(
            op="insert_after",
            after_block_id=blocks[-1].id if blocks else None,
            payload={"block_type": "paragraph", "text": text[:20_000]},
            citations=(citations or [])[:20],
        )
        patch = create_patch(
            scope.db,
            scope.runtime_context,
            scope.project_id,
            PatchCreate(
                base_content_version_id=version.id,
                operations=[operation],
                summary=summary[:2_000],
                idempotency_key=(
                    f"deepagents:{scope.runtime_context.workspace_id}:"
                    f"{scope.project_id}:{version.id}:{summary[:80]}"
                ),
            ),
        )
        return {"patch_id": patch.id, "status": patch.status}

    return {
        "validate_current_content": validate_current_content,
        "read_current_content": read_current_content,
        "propose_text_patch": propose_text_patch,
    }
