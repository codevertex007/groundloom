"""Scoped evidence tools for the agent and its research subagent."""

from collections.abc import Callable
from typing import Any

from ...errors import GroundloomError
from ...services import project_detail, read_passage, search_evidence
from ..contracts import ToolContext


def build_source_tools(scope: ToolContext) -> dict[str, Callable[..., Any]]:
    def search_source_passages(query: str) -> dict[str, Any]:
        """Search only source versions pinned to this project."""

        return search_evidence(
            scope.db,
            scope.runtime_context,
            scope.project_id,
            query,
            limit=8,
            settings=scope.settings,
        ).model_dump()

    def read_source_passage(source_version_id: str, passage_id: str) -> dict[str, Any]:
        """Read one immutable passage after enforcing project source scope."""

        snapshot = project_detail(scope.db, scope.runtime_context, scope.project_id)
        if source_version_id not in snapshot["config"].get("source_version_ids", []):
            raise GroundloomError(
                "PERMISSION_DENIED",
                "The passage is outside the project source scope.",
                403,
            )
        return read_passage(scope.db, scope.runtime_context, source_version_id, passage_id)

    return {
        "search_source_passages": search_source_passages,
        "read_source_passage": read_source_passage,
    }
