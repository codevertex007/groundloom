"""Deep Agents-compatible policy, budget, cancellation, and progress middleware."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import SystemMessage

from .budgets import BudgetExceeded
from .cancellation import ensure_not_cancelled
from .events import emit, runtime_context
from .policy import ToolPolicy


def _append_system_text(message: SystemMessage | None, text: str) -> SystemMessage:
    if message is None:
        return SystemMessage(content=text)
    content = message.content
    if isinstance(content, str):
        return SystemMessage(content=f"{content}\n\n{text}")
    return SystemMessage(content=[*content, {"type": "text", "text": f"\n\n{text}"}])


def _tool_metadata(request: Any) -> tuple[str, str]:
    call = getattr(request, "tool_call", {})
    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
    call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
    return str(name or "unknown")[:120], str(call_id or "unknown")[:160]


class PolicyMiddleware(AgentMiddleware):
    def __init__(self, policy: ToolPolicy, policy_prompt: str):
        self.policy = policy
        self.policy_prompt = policy_prompt

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        request = request.override(
            system_message=_append_system_text(request.system_message, self.policy_prompt),
            tools=self.policy.visible(list(request.tools)),
        )
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        request = request.override(
            system_message=_append_system_text(request.system_message, self.policy_prompt),
            tools=self.policy.visible(list(request.tools)),
        )
        return await handler(request)

    def before_model(self, state: AgentState[Any], runtime: Any) -> None:
        ensure_not_cancelled(runtime)


class BudgetMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        try:
            runtime_context(request.runtime)["tool_budget"].consume()
        except BudgetExceeded:
            emit(request.runtime, "agent.progress", {"stage": "budget_exhausted"})
            raise
        ensure_not_cancelled(request.runtime)
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        try:
            runtime_context(request.runtime)["tool_budget"].consume()
        except BudgetExceeded:
            emit(request.runtime, "agent.progress", {"stage": "budget_exhausted"})
            raise
        ensure_not_cancelled(request.runtime)
        return await handler(request)


class ProgressMiddleware(AgentMiddleware):
    """Emit safe lifecycle metadata without model text or tool arguments."""

    def before_agent(self, state: AgentState[Any], runtime: Any) -> None:
        context = runtime_context(runtime)
        emit(runtime, "agent.progress", {"stage": "started", "thread": context["thread_id"]})

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        emit(request.runtime, "agent.progress", {"stage": "model"})
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        emit(request.runtime, "agent.progress", {"stage": "model"})
        return await handler(request)

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        return self._run(request, handler)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        return await self._arun(request, handler)

    def _run(self, request: Any, handler: Any) -> Any:
        name, call_id = _tool_metadata(request)
        event = {"tool_name": name, "call_id": call_id}
        emit(request.runtime, "tool.started", event)
        if name == "task":
            emit(request.runtime, "subagent.started", event)
        try:
            result = handler(request)
        except Exception:
            self._complete(request.runtime, event, name, "failed")
            raise
        self._complete(request.runtime, event, name, "completed")
        return result

    async def _arun(self, request: Any, handler: Any) -> Any:
        name, call_id = _tool_metadata(request)
        event = {"tool_name": name, "call_id": call_id}
        emit(request.runtime, "tool.started", event)
        if name == "task":
            emit(request.runtime, "subagent.started", event)
        try:
            result = await handler(request)
        except Exception:
            self._complete(request.runtime, event, name, "failed")
            raise
        self._complete(request.runtime, event, name, "completed")
        return result

    @staticmethod
    def _complete(runtime: Any, event: dict[str, str], name: str, status: str) -> None:
        payload = {**event, "status": status}
        emit(runtime, "tool.completed", payload)
        if name == "task":
            emit(runtime, "subagent.completed", payload)


def build_harness_middleware(policy: ToolPolicy, policy_prompt: str) -> list[AgentMiddleware]:
    return [PolicyMiddleware(policy, policy_prompt), BudgetMiddleware(), ProgressMiddleware()]
