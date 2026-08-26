"""Shared contracts between the AI harness and deterministic product services."""

from dataclasses import dataclass
from typing import TypedDict

from groundloom_harness import (
    BudgetCounter,
    CancellationCheck,
    EventSink,
)

from .ports import AgentServicePort

ProgressCallback = EventSink
CancelCheck = CancellationCheck


class AgentConfigurationError(RuntimeError):
    """Raised when the agent runtime cannot start due to fixed configuration.

    Distinct from provider/network failures: retrying without changing
    configuration can never succeed, so callers must not apply the generic
    retry-with-backoff policy to this exception.
    """


class AgentRuntimeContext(TypedDict):
    """Transient trusted context supplied by the application, never by the model."""

    workspace_id: str
    project_id: str
    thread_id: str
    event_sink: EventSink | None
    cancellation_check: CancellationCheck | None
    tool_budget: BudgetCounter


@dataclass(frozen=True)
class ToolContext:
    """Authorized service handles captured when the graph's tools are built."""

    services: AgentServicePort


@dataclass(frozen=True)
class AgentDefinition:
    name: str = "groundloom-project-agent"
    version: str = "groundloom-project-agent.v1"
    prompt_version: str = "groundloom.prompt.v1"
    tool_contract_version: str = "groundloom.tools.v1"
