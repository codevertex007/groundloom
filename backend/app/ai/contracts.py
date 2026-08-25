"""Shared contracts between the AI harness and deterministic product services."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from ..config import Settings

ProgressCallback = Callable[[str, dict[str, Any]], None]
CancelCheck = Callable[[], bool]


class AgentRuntimeContext(TypedDict):
    """Transient trusted context supplied by the application, never by the model."""

    workspace_id: str
    project_id: str
    thread_key: str
    settings: Settings
    progress_callback: ProgressCallback | None
    cancel_check: CancelCheck | None
    max_tool_calls: int
    tool_calls_used: int


@dataclass(frozen=True)
class ToolContext:
    """Authorized service handles captured when the graph's tools are built."""

    db: Any
    runtime_context: Any
    project_id: str
    settings: Settings


@dataclass(frozen=True)
class AgentDefinition:
    name: str = "groundloom-project-agent"
    version: str = "groundloom-project-agent.v1"
    prompt_version: str = "groundloom.prompt.v1"
    tool_contract_version: str = "groundloom.tools.v1"
