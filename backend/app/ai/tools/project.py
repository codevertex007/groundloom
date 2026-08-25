"""Project-scoped read tools for the primary agent."""

from collections.abc import Callable
from typing import Any

from ..contracts import ToolContext


def build_project_tools(scope: ToolContext) -> list[Callable[..., Any]]:
    def get_project_snapshot() -> dict[str, Any]:
        """Read a bounded snapshot of the authorized project state."""

        return scope.services.project_snapshot()

    def list_project_skills() -> list[dict[str, Any]]:
        """Return metadata for skill versions selected by this project."""

        return scope.services.project_skills()

    return [get_project_snapshot, list_project_skills]
