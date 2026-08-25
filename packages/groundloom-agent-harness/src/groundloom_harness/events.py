"""Bounded lifecycle-event helpers that never include model or tool payloads."""

from typing import Any, cast

from .context import EventSink, HarnessRuntimeContext


def runtime_context(runtime: Any) -> HarnessRuntimeContext:
    context = getattr(runtime, "context", None)
    if not isinstance(context, dict):
        raise RuntimeError("Trusted agent runtime context is required")
    required = {"thread_id", "tool_budget"}
    if not required.issubset(context):
        raise RuntimeError("Trusted agent runtime context is incomplete")
    return cast(HarnessRuntimeContext, context)


def emit(runtime: Any, event_type: str, payload: dict[str, Any]) -> None:
    sink: EventSink | None = runtime_context(runtime).get("event_sink")
    if sink is not None:
        sink(event_type[:120], payload)
