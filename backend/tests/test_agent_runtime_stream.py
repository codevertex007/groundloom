from types import SimpleNamespace

from app.agent_runtime import consume_provider_stream


def test_provider_stream_projects_bounded_tool_and_subagent_progress():
    events: list[tuple[str, dict]] = []
    stream = [
        (
            "updates",
            {
                "agent": {
                    "messages": [
                        SimpleNamespace(
                            id="ai-1",
                            type="ai",
                            tool_calls=[{"id": "call-1", "name": "task", "args": {"secret": "no"}}],
                        )
                    ]
                }
            },
        ),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        SimpleNamespace(id="tool-1", type="tool", tool_call_id="call-1", name="task")
                    ]
                }
            },
        ),
        (
            "messages",
            (SimpleNamespace(id="ai-2", type="ai", content="private model text"), {"langgraph_node": "agent"}),
        ),
        (
            "updates",
            {
                "agent": {
                    "messages": [
                        SimpleNamespace(id="ai-2", type="ai", content="private model text")
                    ]
                }
            },
        ),
    ]

    result = consume_provider_stream(stream, progress_callback=lambda event, payload: events.append((event, payload)))

    event_types = [event for event, _payload in events]
    assert "agent.progress" in event_types
    assert "tool.started" in event_types
    assert "tool.completed" in event_types
    assert "subagent.started" in event_types
    assert "subagent.completed" in event_types
    assert all("private model text" not in str(payload) for _event, payload in events)
    assert [getattr(message, "id", None) for message in result["messages"]] == ["ai-1", "tool-1", "ai-2"]


def test_provider_stream_stops_between_chunks_when_cancelled():
    events: list[tuple[str, dict]] = []
    checks = 0

    def cancel_check() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    result = consume_provider_stream(
        iter(
            [
                ("updates", {"agent": {"messages": []}}),
                ("updates", {"tools": {"messages": []}}),
            ]
        ),
        progress_callback=lambda event, payload: events.append((event, payload)),
        cancel_check=cancel_check,
    )

    assert result["cancelled"] is True
    assert checks == 2
    assert any(event == "agent.progress" for event, _payload in events)
