"""Ordered middleware assembly shared by the primary agent and its subagents.

Registered as a deepagents ``HarnessProfile.extra_middleware`` factory (see
``agent.py``) rather than passed as the composition root's own inline
middleware list: ``extra_middleware`` is the extension point the framework
threads into every stack it assembles — the main agent, the auto-added
general-purpose subagent, and Groundloom's own declarative subagents. The
inline list only reaches the main agent, which left tool-call budget
enforcement, cancellation checks, and progress events unenforced inside
delegated subagent work.
"""

from groundloom_harness import ToolPolicy
from groundloom_harness.middleware import build_harness_middleware
from langchain.agents.middleware import AgentMiddleware

from ..prompt_loader import load_prompt


def build_middleware_stack() -> list[AgentMiddleware]:
    """Return a fresh instance of the application middleware stack.

    Called as a zero-arg factory by ``HarnessProfile.extra_middleware`` so
    each assembled stack (main agent, each subagent) gets its own instances
    rather than sharing mutable state across concurrent runs.
    """

    return build_harness_middleware(
        ToolPolicy(),
        load_prompt("middleware_policy.txt"),
    )
