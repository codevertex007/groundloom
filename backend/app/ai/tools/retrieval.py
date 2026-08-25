"""Model-facing retrieval tools backed by an authorized application port."""

from collections.abc import Callable
from typing import Any

from ..contracts import ToolContext


def build_source_tools(scope: ToolContext) -> dict[str, Callable[..., Any]]:
    def search_source_passages(query: str) -> dict[str, Any]:
        """Search only source versions pinned to this project."""

        return scope.services.search_source_passages(query, limit=8)

    def read_source_passage(source_version_id: str, passage_id: str) -> dict[str, Any]:
        """Read one immutable passage after enforcing project source scope."""

        return scope.services.read_source_passage(source_version_id, passage_id)

    return {
        "search_source_passages": search_source_passages,
        "read_source_passage": read_source_passage,
    }
