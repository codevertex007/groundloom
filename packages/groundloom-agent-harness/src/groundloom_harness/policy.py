"""Explicit model-visible tool policy."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolPolicy:
    """Allow a bounded tool surface while default-denying dangerous tools."""

    excluded_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"write_file", "edit_file", "delete", "glob", "grep", "execute"}
        )
    )

    def visible(self, tools: list[Any]) -> list[Any]:
        return [tool for tool in tools if getattr(tool, "name", None) not in self.excluded_tools]
