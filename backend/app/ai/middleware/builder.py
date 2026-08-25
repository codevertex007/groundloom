"""Ordered middleware assembly for the primary project agent."""

from groundloom_harness import ToolPolicy
from groundloom_harness.middleware import build_harness_middleware
from langchain.agents.middleware import AgentMiddleware

from ..prompt_loader import load_prompt


def build_middleware_stack() -> list[AgentMiddleware]:
    """Return the explicit application middleware stack passed to Deep Agents."""

    return build_harness_middleware(
        ToolPolicy(),
        load_prompt("middleware_policy.txt"),
    )
