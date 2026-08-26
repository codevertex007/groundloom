"""Targeted behavior tests for the reusable harness middleware hooks.

These exercise the actual production middleware classes (PolicyMiddleware,
BudgetMiddleware, ProgressMiddleware) against the request/runtime shapes
LangChain's AgentMiddleware passes at call time. No existing test drives
these hook methods directly; test_reusable_agent_harness.py only covers the
underlying primitives (BudgetCounter, ToolPolicy.visible) in isolation, and
test_optional_provider_contracts.py never triggers an actual tool call
through a compiled graph, so the wrap_tool_call/wrap_model_call bodies were
previously unexercised in this state (budget exhaustion, tool filtering,
cancellation-mid-run).
"""

from types import SimpleNamespace

import pytest
from groundloom_harness import BudgetCounter, BudgetExceeded, ToolPolicy

# groundloom_harness.middleware imports langchain.agents.middleware at module
# level (these classes subclass AgentMiddleware), so importing it here
# unconditionally would fail collection of this whole file wherever the
# optional `agent` extra isn't installed, rather than skipping gracefully.
pytest.importorskip("langchain.agents.middleware")
from groundloom_harness.middleware import (  # noqa: E402
    BudgetMiddleware,
    PolicyMiddleware,
    ProgressMiddleware,
)


class FakeModelRequest:
    def __init__(self, tools, system_message=None):
        self.tools = tools
        self.system_message = system_message
        self.overridden_with = None

    def override(self, **overrides):
        self.overridden_with = overrides
        return SimpleNamespace(**{**self.__dict__, **overrides})


class FakeTool:
    def __init__(self, name):
        self.name = name


class FakeToolCallRequest:
    def __init__(self, runtime, tool_call):
        self.runtime = runtime
        self.tool_call = tool_call


def make_runtime(*, budget_limit=3, cancelled=False, events=None):
    calls = []

    def cancel_check():
        return cancelled

    def sink(event_type, payload):
        calls.append((event_type, payload))

    context = {
        "thread_id": "thread-1",
        "event_sink": sink,
        "cancellation_check": cancel_check,
        "tool_budget": BudgetCounter(budget_limit),
    }
    runtime = SimpleNamespace(context=context)
    return runtime, calls


def test_policy_middleware_strips_excluded_tools_from_model_request():
    tools = [FakeTool("read_file"), FakeTool("write_file"), FakeTool("search_source_passages")]
    request = FakeModelRequest(tools=tools)
    middleware = PolicyMiddleware(ToolPolicy(), "Follow the grounding policy.")

    handler_seen: dict[str, object] = {}

    def handler(overridden_request):
        handler_seen["tools"] = [t.name for t in overridden_request.tools]
        handler_seen["system_message"] = overridden_request.system_message
        return "ok"

    result = middleware.wrap_model_call(request, handler)

    assert result == "ok"
    assert handler_seen["tools"] == ["read_file", "search_source_passages"]
    assert "write_file" not in handler_seen["tools"]
    assert "Follow the grounding policy." in getattr(handler_seen["system_message"], "content", "")


def test_budget_middleware_allows_calls_within_budget_and_blocks_over_budget():
    runtime, events = make_runtime(budget_limit=2)
    middleware = BudgetMiddleware()

    def handler(_request):
        return "tool-result"

    request = FakeToolCallRequest(runtime, {"name": "search_source_passages", "id": "call-1"})

    assert middleware.wrap_tool_call(request, handler) == "tool-result"
    assert middleware.wrap_tool_call(request, handler) == "tool-result"

    with pytest.raises(BudgetExceeded):
        middleware.wrap_tool_call(request, handler)

    assert runtime.context["tool_budget"].used == 2
    assert ("agent.progress", {"stage": "budget_exhausted"}) in events


def test_budget_middleware_blocks_before_handler_runs_when_cancelled():
    runtime, _events = make_runtime(budget_limit=5, cancelled=True)
    middleware = BudgetMiddleware()
    handler_calls = []

    def handler(_request):
        handler_calls.append(1)
        return "should-not-run"

    request = FakeToolCallRequest(runtime, {"name": "search_source_passages", "id": "call-1"})

    with pytest.raises(RuntimeError, match="cancelled"):
        middleware.wrap_tool_call(request, handler)

    assert handler_calls == [], "handler must not execute once cancellation is observed"
    assert runtime.context["tool_budget"].used == 0, "cancellation is checked before budget is consumed"


def test_progress_middleware_emits_lifecycle_events_around_tool_and_subagent_calls():
    runtime, events = make_runtime()
    middleware = ProgressMiddleware()

    def handler(_request):
        return "result"

    request = FakeToolCallRequest(runtime, {"name": "task", "id": "call-9"})
    middleware.wrap_tool_call(request, handler)

    event_types = [event for event, _payload in events]
    assert event_types == [
        "tool.started",
        "subagent.started",
        "tool.completed",
        "subagent.completed",
    ]


def test_progress_middleware_emits_failed_status_when_handler_raises():
    runtime, events = make_runtime()
    middleware = ProgressMiddleware()

    def failing_handler(_request):
        raise ValueError("boom")

    request = FakeToolCallRequest(runtime, {"name": "search_source_passages", "id": "call-2"})

    with pytest.raises(ValueError, match="boom"):
        middleware.wrap_tool_call(request, failing_handler)

    completed = [payload for event, payload in events if event == "tool.completed"]
    assert completed == [{"tool_name": "search_source_passages", "call_id": "call-2", "status": "failed"}]
