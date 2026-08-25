"""Security and execution-budget middleware for the project agent."""

from typing import Any

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware

from ..prompt_loader import load_prompt
from .context import emit, runtime_context

_FORBIDDEN_TOOLS = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"}
)


class GroundloomPolicyMiddleware(AgentMiddleware):
    """Adds the immutable Groundloom safety policy and filters infrastructure tools."""

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        visible_tools = [
            tool
            for tool in request.tools
            if getattr(tool, "name", None) not in _FORBIDDEN_TOOLS
        ]
        request = request.override(
            system_message=append_to_system_message(
                request.system_message,
                load_prompt("middleware_policy.txt"),
            ),
            tools=visible_tools,
        )
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        visible_tools = [
            tool
            for tool in request.tools
            if getattr(tool, "name", None) not in _FORBIDDEN_TOOLS
        ]
        request = request.override(
            system_message=append_to_system_message(
                request.system_message,
                load_prompt("middleware_policy.txt"),
            ),
            tools=visible_tools,
        )
        return await handler(request)

    def before_model(self, state: dict[str, Any], runtime: Any) -> None:
        context = runtime_context(runtime)
        cancel_check = context.get("cancel_check")
        if cancel_check is not None and cancel_check():
            raise RuntimeError("Groundloom agent run was cancelled")


class ToolBudgetMiddleware(AgentMiddleware):
    """Enforces the application tool-call budget from trusted runtime context."""

    def before_model(self, state: dict[str, Any], runtime: Any) -> None:
        context = runtime_context(runtime)
        if context["tool_calls_used"] > context["max_tool_calls"]:
            emit(runtime, "agent.progress", {"stage": "budget_exhausted"})
            raise RuntimeError("Groundloom agent tool-call budget exceeded")

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        context = runtime_context(request.runtime)
        context["tool_calls_used"] += 1
        if context["tool_calls_used"] > context["max_tool_calls"]:
            raise RuntimeError("Groundloom agent tool-call budget exceeded")
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        context = runtime_context(request.runtime)
        context["tool_calls_used"] += 1
        if context["tool_calls_used"] > context["max_tool_calls"]:
            raise RuntimeError("Groundloom agent tool-call budget exceeded")
        return await handler(request)
