"""Durable-progress projection middleware for model and tool lifecycle hooks."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from .context import emit, runtime_context


def _tool_name(request: Any) -> str:
    call = getattr(request, "tool_call", {})
    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
    return str(name or "unknown")[:120]


def _tool_call_id(request: Any) -> str:
    call = getattr(request, "tool_call", {})
    value = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
    return str(value or "unknown")[:160]


class ProgressMiddleware(AgentMiddleware):
    """Emits bounded event metadata without forwarding model text or arguments."""

    def before_agent(self, state: dict[str, Any], runtime: Any) -> None:
        context = runtime_context(runtime)
        emit(runtime, "agent.progress", {"stage": "started", "thread": context["thread_key"]})

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        emit(request.runtime, "agent.progress", {"stage": "model"})
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        emit(request.runtime, "agent.progress", {"stage": "model"})
        return await handler(request)

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = _tool_name(request)
        call_id = _tool_call_id(request)
        event = {"tool_name": name, "call_id": call_id}
        emit(request.runtime, "tool.started", event)
        if name == "task":
            emit(request.runtime, "subagent.started", event)
        try:
            result = handler(request)
        except Exception:
            emit(request.runtime, "tool.completed", {**event, "status": "failed"})
            if name == "task":
                emit(request.runtime, "subagent.completed", {**event, "status": "failed"})
            raise
        emit(request.runtime, "tool.completed", {**event, "status": "completed"})
        if name == "task":
            emit(request.runtime, "subagent.completed", {**event, "status": "completed"})
        return result

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = _tool_name(request)
        call_id = _tool_call_id(request)
        event = {"tool_name": name, "call_id": call_id}
        emit(request.runtime, "tool.started", event)
        if name == "task":
            emit(request.runtime, "subagent.started", event)
        try:
            result = await handler(request)
        except Exception:
            emit(request.runtime, "tool.completed", {**event, "status": "failed"})
            if name == "task":
                emit(request.runtime, "subagent.completed", {**event, "status": "failed"})
            raise
        emit(request.runtime, "tool.completed", {**event, "status": "completed"})
        if name == "task":
            emit(request.runtime, "subagent.completed", {**event, "status": "completed"})
        return result
