"""Approved workspace memory tools."""

from collections.abc import Callable
from typing import Any

from ..contracts import ToolContext


def build_memory_tools(scope: ToolContext) -> list[Callable[..., Any]]:
    def read_workspace_memory() -> list[dict[str, Any]]:
        """Read approved user-scoped memory without exposing source text."""

        return scope.services.read_workspace_memory()

    return [read_workspace_memory]
