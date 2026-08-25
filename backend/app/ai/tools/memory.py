"""Approved workspace memory tools."""

from collections.abc import Callable
from typing import Any

from ...services import read_memory
from ..contracts import ToolContext


def build_memory_tools(scope: ToolContext) -> list[Callable[..., Any]]:
    def read_workspace_memory() -> list[dict[str, Any]]:
        """Read approved user-scoped memory without exposing source text."""

        return read_memory(scope.db, scope.runtime_context)

    return [read_workspace_memory]
