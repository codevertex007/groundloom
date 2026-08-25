"""Ordered middleware assembly for the primary project agent."""

from typing import Any

from .progress import ProgressMiddleware
from .safety import GroundloomPolicyMiddleware, ToolBudgetMiddleware


def build_middleware_stack() -> list[Any]:
    """Return the explicit application middleware stack passed to Deep Agents."""

    return [
        GroundloomPolicyMiddleware(),
        ToolBudgetMiddleware(),
        ProgressMiddleware(),
    ]
