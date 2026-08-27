"""Typed content read, validation, and proposal LangChain tools."""

from typing import Any

from langchain_core.tools import BaseTool, tool

from ..contracts import ToolContext
from .schemas import CitationReferenceInput, ProposeTextPatchInput


def build_content_tools(scope: ToolContext) -> dict[str, BaseTool]:
    @tool
    def validate_current_content() -> dict[str, Any]:
        """Run deterministic validation against the current content version.

        Use after drafting or before proposing completion. This is read-only;
        semantic model judgment never replaces these invariant checks.
        """

        return scope.services.validate_current_content()

    @tool
    def read_current_content() -> dict[str, Any]:
        """Read the authorized project's current typed content and block IDs.

        Use before proposing a change. This is read-only and returns a bounded
        versioned view rather than mutable agent state.
        """

        return scope.services.read_current_content()

    @tool(args_schema=ProposeTextPatchInput)
    def propose_text_patch(
        summary: str,
        text: str,
        citations: list[CitationReferenceInput] | None = None,
    ) -> dict[str, Any]:
        """Create a bounded reviewable text patch against the current version.

        Use only after reading current content and retrieving evidence. This
        creates a non-canonical proposal; it never accepts or commits content.
        """

        serialized_citations = (
            [citation.model_dump(exclude_none=True) for citation in citations]
            if citations is not None
            else None
        )
        return scope.services.propose_text_patch(summary, text, serialized_citations)

    return {
        "validate_current_content": validate_current_content,
        "read_current_content": read_current_content,
        "propose_text_patch": propose_text_patch,
    }
