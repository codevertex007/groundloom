"""Compatibility imports for the AI runtime.

The implementation lives in :mod:`app.ai.agent_runtime`. This stable facade
keeps existing backend integrations and third-party probes working while
making the AI ownership boundary explicit.
"""

from .ai.agent_runtime import (
    AgentDefinition,
    AgentRuntime,
    DeepAgentsAgentRuntime,
    LocalDeterministicAgentRuntime,
    build_agent_runtime,
    consume_provider_stream,
)
from .checkpoints import build_checkpoint_provider

__all__ = [
    "AgentDefinition",
    "AgentRuntime",
    "DeepAgentsAgentRuntime",
    "LocalDeterministicAgentRuntime",
    "build_agent_runtime",
    "consume_provider_stream",
    "build_checkpoint_provider",
]
