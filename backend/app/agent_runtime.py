"""Primary project-agent runtime boundary.

Groundloom keeps the semantic loop in one project-scoped collaborator. The local
adapter is deterministic for development and tests; deployments can select an
installed Deep Agents provider through the same factory without changing the
product contracts or giving the model infrastructure authority.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentDefinition:
    name: str = "groundloom-project-agent"
    version: str = "groundloom-project-agent.v1"
    prompt_version: str = "groundloom.prompt.v1"
    tool_contract_version: str = "groundloom.tools.v1"


class AgentRuntime:
    definition = AgentDefinition()

    def capabilities(self) -> dict[str, Any]:
        return {
            "adaptive_loop": True,
            "persistent_thread": True,
            "planning": True,
            "typed_tools": True,
            "dynamic_delegation": True,
            "canonical_commit": False,
            "unrestricted_shell": False,
            "scope_from_model": False,
        }


class LocalDeterministicAgentRuntime(AgentRuntime):
    """Safe local/test runtime used when no model credentials are configured."""

    provider = "local"


def build_agent_runtime(provider: str) -> AgentRuntime:
    if provider == "local":
        return LocalDeterministicAgentRuntime()
    try:
        import deepagents  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "The configured Deep Agents provider is not installed; use the local adapter or install the pinned provider extra."
        ) from exc
    # The optional integration is intentionally kept behind this narrow seam.
    # The installed package/version must be verified before enabling it in a deployment.
    raise RuntimeError("Deep Agents provider integration requires a verified deployment adapter.")
