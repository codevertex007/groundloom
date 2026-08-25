"""Framework-neutral trusted runtime context contracts."""

from collections.abc import Callable
from typing import Any, TypedDict

from .budgets import BudgetCounter

EventSink = Callable[[str, dict[str, Any]], None]
CancellationCheck = Callable[[], bool]


class HarnessRuntimeContext(TypedDict):
    """Minimum hidden context consumed by reusable harness middleware."""

    thread_id: str
    event_sink: EventSink | None
    cancellation_check: CancellationCheck | None
    tool_budget: BudgetCounter
