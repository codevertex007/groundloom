"""Typed assembly of the Groundloom tool surface."""

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from ..contracts import ToolContext
from .content import build_content_tools
from .memory import build_memory_tools
from .project import build_project_tools
from .retrieval import build_source_tools


@dataclass(frozen=True)
class GroundloomToolset:
    all_tools: tuple[BaseTool, ...]
    read_only: tuple[BaseTool, ...]
    source_research: tuple[BaseTool, ...]
    citation_audit: tuple[BaseTool, ...]
    module_writing: tuple[BaseTool, ...]


def build_toolset(scope: ToolContext) -> GroundloomToolset:
    project_tools = build_project_tools(scope)
    source_tools = build_source_tools(scope)
    content_tools = build_content_tools(scope)
    memory_tools = build_memory_tools(scope)

    read_only = (
        source_tools["search_source_passages"],
        source_tools["read_source_passage"],
        content_tools["read_current_content"],
        *memory_tools,
        project_tools[1],
    )
    all_tools = (
        *project_tools,
        *source_tools.values(),
        *content_tools.values(),
        *memory_tools,
    )
    return GroundloomToolset(
        all_tools=all_tools,
        read_only=read_only,
        source_research=(
            source_tools["search_source_passages"],
            source_tools["read_source_passage"],
        ),
        citation_audit=(
            content_tools["read_current_content"],
            source_tools["read_source_passage"],
            source_tools["search_source_passages"],
        ),
        module_writing=(
            content_tools["read_current_content"],
            source_tools["search_source_passages"],
            source_tools["read_source_passage"],
            content_tools["propose_text_patch"],
        ),
    )
