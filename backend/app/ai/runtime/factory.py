"""Single runtime factory; provider-specific dependencies stay lazy."""

from ...config import Settings
from .local import AgentRuntime, LocalDeterministicAgentRuntime


def build_agent_runtime(provider: str, settings: Settings | None = None) -> AgentRuntime:
    if provider == "local":
        return LocalDeterministicAgentRuntime()
    if settings is None:
        raise RuntimeError("A validated Settings object is required for a production agent runtime")
    from ..agent import DeepAgentsAgentRuntime

    return DeepAgentsAgentRuntime(settings)
