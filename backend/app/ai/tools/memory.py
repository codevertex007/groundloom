"""Approved workspace-memory LangChain tools."""

from typing import Any

from langchain_core.tools import BaseTool, tool

from ..contracts import ToolContext


def build_memory_tools(scope: ToolContext) -> list[BaseTool]:
    @tool
    def read_workspace_memory() -> list[dict[str, Any]]:
        """Read bounded approved memory for the current user and workspace.

        Use only for stable preferences or terminology. This is read-only and
        never returns source text, drafts, or another user's memory.
        """

        return scope.services.read_workspace_memory()

    return [read_workspace_memory]
