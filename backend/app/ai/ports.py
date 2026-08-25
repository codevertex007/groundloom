"""Application capabilities consumed by model-facing tools.

The AI package owns these contracts. Backend integrations implement them after
authorization and tenant scope have been established by trusted application code.
"""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from groundloom_harness.skills_backend import SkillPackage


class AgentServicePort(Protocol):
    def list_packages(self) -> tuple["SkillPackage", ...]: ...

    def project_snapshot(self) -> dict[str, Any]: ...

    def project_skills(self) -> list[dict[str, Any]]: ...

    def search_source_passages(self, query: str, limit: int = 8) -> dict[str, Any]: ...

    def read_source_passage(self, source_version_id: str, passage_id: str) -> dict[str, Any]: ...

    def read_current_content(self) -> dict[str, Any]: ...

    def validate_current_content(self) -> dict[str, Any]: ...

    def propose_text_patch(
        self,
        summary: str,
        text: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def read_workspace_memory(self) -> list[dict[str, Any]]: ...
