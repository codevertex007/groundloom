"""Small helpers for reading trusted application context in middleware."""

from typing import Any, cast

from ..contracts import AgentRuntimeContext, ProgressCallback


def runtime_context(runtime: Any) -> AgentRuntimeContext:
    context = getattr(runtime, "context", None)
    if not isinstance(context, dict):
        raise RuntimeError("Groundloom agent context is required")
    required = {"workspace_id", "project_id", "thread_key", "settings"}
    if not required.issubset(context):
        raise RuntimeError("Groundloom agent context is incomplete")
    return cast(AgentRuntimeContext, context)


def emit(runtime: Any, event_type: str, payload: dict[str, Any]) -> None:
    callback: ProgressCallback | None = runtime_context(runtime).get("progress_callback")
    if callback is not None:
        callback(event_type, payload)
