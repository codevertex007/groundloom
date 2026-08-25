"""Cancellation checks shared by middleware hooks."""

from typing import Any

from .events import runtime_context


def ensure_not_cancelled(runtime: Any) -> None:
    check = runtime_context(runtime).get("cancellation_check")
    if check is not None and check():
        raise RuntimeError("Agent run was cancelled")
