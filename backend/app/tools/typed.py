"""Compatibility facade for the scoped AI tool registry."""

from ..ai.tools.typed import (
    TOOL_REGISTRY,
    ToolSpec,
    get_project_snapshot,
    propose_block_patch,
    read_content_blocks,
    search_source_passages,
)

__all__ = [
    "TOOL_REGISTRY",
    "ToolSpec",
    "get_project_snapshot",
    "propose_block_patch",
    "read_content_blocks",
    "search_source_passages",
]
