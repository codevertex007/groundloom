"""Project-scoped read tools for the primary agent."""

from collections.abc import Callable
from typing import Any

from ...services import list_skills, project_detail
from ..contracts import ToolContext


def build_project_tools(scope: ToolContext) -> list[Callable[..., Any]]:
    def get_project_snapshot() -> dict[str, Any]:
        """Read a bounded snapshot of the authorized project state."""

        return project_detail(scope.db, scope.runtime_context, scope.project_id)

    def list_project_skills() -> list[dict[str, Any]]:
        """Return metadata for skill versions selected by this project."""

        snapshot = project_detail(scope.db, scope.runtime_context, scope.project_id)
        selected = set(snapshot["config"].get("skill_version_ids", []))
        return [
            skill
            for skill in list_skills(scope.db, scope.runtime_context)
            if any(version["id"] in selected for version in skill["versions"])
        ]

    return [get_project_snapshot, list_project_skills]
