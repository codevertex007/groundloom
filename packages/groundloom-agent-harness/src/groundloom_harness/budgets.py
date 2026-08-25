"""Concurrency-safe execution budgets shared by tools and subagents."""

from dataclasses import dataclass, field
from threading import Lock


class BudgetExceeded(RuntimeError):
    """Raised before a tool executes beyond its trusted runtime budget."""


@dataclass
class BudgetCounter:
    """Atomic bounded counter suitable for parallel tool execution."""

    limit: int
    _used: int = 0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("Budget limit must be positive")

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def consume(self, amount: int = 1) -> int:
        if amount < 1:
            raise ValueError("Budget consumption must be positive")
        with self._lock:
            if self._used + amount > self.limit:
                raise BudgetExceeded("Agent tool-call budget exceeded")
            self._used += amount
            return self._used
