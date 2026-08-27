"""Project-scoped LangChain tools for the primary agent."""

from typing import Any

from langchain_core.tools import BaseTool, tool

from ..contracts import ToolContext


def build_project_tools(scope: ToolContext) -> list[BaseTool]:
    @tool
    def get_project_snapshot() -> dict[str, Any]:
        """Read the authorized project's bounded state snapshot.

        Use before project-specific reasoning. This is read-only; never use it
        to infer or broaden tenant scope.
        """

        return scope.services.project_snapshot()

    @tool
    def list_project_skills() -> list[dict[str, Any]]:
        """List metadata for immutable skill versions selected by this project.

        Use for skill discovery. This is read-only and does not publish, edit,
        or select skills.
        """

        return scope.services.project_skills()

    return [get_project_snapshot, list_project_skills]
