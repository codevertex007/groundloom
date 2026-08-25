"""Safe projection of LangGraph provider streams into product events."""

from collections.abc import Callable, Iterable
from typing import Any

ProgressCallback = Callable[[str, dict[str, Any]], None]
CancelCheck = Callable[[], bool]


def _message_value(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _message_id(message: Any) -> str | None:
    value = _message_value(message, "id")
    return str(value) if value else None


def _message_type(message: Any) -> str:
    value = _message_value(message, "type")
    if value:
        return str(value)
    class_name = type(message).__name__.lower()
    if "tool" in class_name:
        return "tool"
    if "human" in class_name:
        return "human"
    if "ai" in class_name:
        return "ai"
    return "message"


def _tool_calls(message: Any) -> list[Any]:
    calls = _message_value(message, "tool_calls", [])
    return list(calls) if isinstance(calls, (list, tuple)) else []


def _tool_name(value: Any) -> str:
    if isinstance(value, dict):
        name = value.get("name") or value.get("tool_name")
    else:
        name = getattr(value, "name", None) or getattr(value, "tool_name", None)
    return str(name)[:120] if name else "unknown"


def _tool_call_id(value: Any) -> str | None:
    if isinstance(value, dict):
        call_id = value.get("id") or value.get("tool_call_id")
    else:
        call_id = getattr(value, "id", None) or getattr(value, "tool_call_id", None)
    return str(call_id)[:160] if call_id else None


def _stream_mode_and_chunk(item: Any) -> tuple[str, Any]:
    """Normalize LangGraph single- and multi-mode stream output."""
    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
        return item[0], item[1]
    return "updates", item


def consume_provider_stream(
    stream: Iterable[Any],
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """Collect a Deep Agents stream while projecting only safe progress metadata.

    Deep Agents/LangGraph emits ``(mode, chunk)`` pairs for multi-mode streams.
    The product stream must never contain model text, tool arguments, source
    passages, or hidden reasoning, so this adapter emits names, node phases,
    and bounded call IDs only. Message state is reconstructed by ID so both
    delta and snapshot-shaped update chunks are accepted.
    """
    state: dict[str, Any] = {}
    messages: list[Any] = []
    message_positions: dict[str, int] = {}
    streamed_messages: list[Any] = []
    streamed_message_positions: dict[str, int] = {}
    emitted_nodes: set[str] = set()
    emitted_tool_starts: set[str] = set()
    emitted_tool_completions: set[str] = set()
    cancelled = False

    def remember_messages(values: Any, target: list[Any], positions: dict[str, int]) -> list[Any]:
        if not isinstance(values, (list, tuple)):
            return []
        normalized = list(values)
        for message in normalized:
            message_id = _message_id(message)
            if message_id is not None and message_id in positions:
                target[positions[message_id]] = message
            else:
                if message_id is not None:
                    positions[message_id] = len(target)
                target.append(message)
        return normalized

    def emit(event_type: str, payload: dict[str, Any]) -> None:
        if progress_callback is not None:
            progress_callback(event_type, payload)

    for item in stream:
        if cancel_check is not None and cancel_check():
            cancelled = True
            break
        mode, chunk = _stream_mode_and_chunk(item)
        if mode == "messages":
            message = chunk[0] if isinstance(chunk, tuple) and chunk else chunk
            metadata = chunk[1] if isinstance(chunk, tuple) and len(chunk) > 1 else {}
            # Token chunks are useful for liveness but are not authoritative
            # state; updates below contain the ordered checkpointed messages.
            remember_messages([message], streamed_messages, streamed_message_positions)
            if isinstance(metadata, dict):
                node = str(metadata.get("langgraph_node") or metadata.get("node") or "model")[:120]
            else:
                node = "model"
            if node not in emitted_nodes:
                emit("agent.progress", {"stage": "model", "node": node})
                emitted_nodes.add(node)
            continue

        if not isinstance(chunk, dict):
            continue
        for node_name, update in chunk.items():
            node = str(node_name)[:120]
            if node not in emitted_nodes:
                emit("agent.progress", {"stage": "node", "node": node})
                emitted_nodes.add(node)
            if not isinstance(update, dict):
                continue
            state.update({key: value for key, value in update.items() if key != "messages"})
            update_messages = remember_messages(update.get("messages"), messages, message_positions)
            for message in update_messages:
                tool_calls = _tool_calls(message)
                for call in tool_calls:
                    call_id = _tool_call_id(call) or f"{node}:{_tool_name(call)}"
                    if call_id in emitted_tool_starts:
                        continue
                    emitted_tool_starts.add(call_id)
                    name = _tool_name(call)
                    emit("tool.started", {"tool_name": name, "call_id": call_id, "node": node})
                    if name == "task":
                        emit(
                            "subagent.started",
                            {"tool_name": name, "call_id": call_id, "node": node},
                        )
                if _message_type(message) == "tool":
                    call_id = _tool_call_id(message) or f"{node}:tool"
                    if call_id not in emitted_tool_completions:
                        emitted_tool_completions.add(call_id)
                        name = _tool_name(message)
                        emit(
                            "tool.completed", {"tool_name": name, "call_id": call_id, "node": node}
                        )
                        if name == "task":
                            emit(
                                "subagent.completed",
                                {"tool_name": name, "call_id": call_id, "node": node},
                            )

    state["messages"] = messages or streamed_messages
    if cancelled:
        state["cancelled"] = True
    return state
