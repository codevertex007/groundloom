"""AI engineering boundary for Groundloom.

Provider adapters, agent runtime behavior, prompt assets, and AI-specific
evaluation code belong here. Product services consume these modules through
narrow contracts and remain responsible for authorization and canonical state.
"""

from .agent_runtime import (
    AgentDefinition,
    AgentRuntime,
    DeepAgentsAgentRuntime,
    LocalDeterministicAgentRuntime,
    build_agent_runtime,
    consume_provider_stream,
)

__all__ = [
    "AgentDefinition",
    "AgentRuntime",
    "DeepAgentsAgentRuntime",
    "LocalDeterministicAgentRuntime",
    "build_agent_runtime",
    "consume_provider_stream",
]
