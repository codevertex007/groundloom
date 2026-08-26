"""Explicit model-visible tool policy."""

from dataclasses import dataclass, field
from typing import Any

# Single source of truth for the DeepAgents built-in tools Groundloom never
# lets a model see: filesystem mutation, filesystem search, and shell
# execution. Referenced both by ToolPolicy's own middleware-level filter (the
# primary agent's model-request tools) and by the deepagents HarnessProfile
# registration (which also reaches subagent stacks) so the two enforcement
# layers cannot silently drift apart.
DEFAULT_EXCLUDED_TOOLS: frozenset[str] = frozenset(
    {"write_file", "edit_file", "delete", "glob", "grep", "execute"}
)


@dataclass(frozen=True)
class ToolPolicy:
    """Allow a bounded tool surface while default-denying dangerous tools."""

    excluded_tools: frozenset[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_TOOLS)

    def visible(self, tools: list[Any]) -> list[Any]:
        return [tool for tool in tools if getattr(tool, "name", None) not in self.excluded_tools]
