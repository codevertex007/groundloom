"""Typed content read, validation, and proposal tools."""

from collections.abc import Callable
from typing import Any

from ..contracts import ToolContext


def build_content_tools(scope: ToolContext) -> dict[str, Callable[..., Any]]:
    def validate_current_content() -> dict[str, Any]:
        """Run deterministic validation without mutating canonical content."""

        return scope.services.validate_current_content()

    def read_current_content() -> dict[str, Any]:
        """Read the current typed content version and its blocks."""

        return scope.services.read_current_content()

    def propose_text_patch(
        summary: str, text: str, citations: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Create a validated reviewable patch; never commit canonical content."""

        return scope.services.propose_text_patch(summary, text, citations)

    return {
        "validate_current_content": validate_current_content,
        "read_current_content": read_current_content,
        "propose_text_patch": propose_text_patch,
    }
