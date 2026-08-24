# Document 09 -- Messages Delta Reducer

**Source file:** `libs/deepagents/deepagents/_messages_reducer.py` (91 lines)
**Tests:** `libs/deepagents/tests/unit_tests/test_messages_reducer.py` (136 lines)
**Wired in:** `libs/deepagents/deepagents/graph.py` via `DeepAgentState`

The messages reducer is the function that determines how the `messages` field in agent state evolves over time. Every time a graph node writes new messages, the reducer decides how those writes merge with the existing conversation history. Deep Agents ships a custom reducer -- `_messages_delta_reducer` -- that replaces LangGraph's default `add_messages` to support delta-based checkpointing with lower storage overhead.

---

## Table of Contents

1. [Purpose and Motivation](#1-purpose-and-motivation)
2. [Key Dependencies](#2-key-dependencies)
3. [Function Signature](#3-function-signature)
4. [The REMOVE_ALL_MESSAGES Sentinel](#4-the-remove_all_messages-sentinel)
5. [Algorithm: Line-by-Line Walkthrough](#5-algorithm-line-by-line-walkthrough)
6. [Message Operations: Dedup, Tombstoning, and Reset](#6-message-operations-dedup-tombstoning-and-reset)
7. [Differences from Upstream LangGraph add_messages](#7-differences-from-upstream-langgraph-add_messages)
8. [Integration with DeltaChannel and snapshot_frequency](#8-integration-with-deltachannel-and-snapshot_frequency)
9. [Tool Message Handling](#9-tool-message-handling)
10. [Edge Cases](#10-edge-cases)
11. [Performance Characteristics](#11-performance-characteristics)
12. [Test Coverage](#12-test-coverage)
13. [Common Pitfalls and Design Rationale](#13-common-pitfalls-and-design-rationale)
14. [What Would Break If You Changed This](#14-what-would-break-if-you-changed-this)
15. [Knowledge Check](#15-knowledge-check)

---

## 1. Purpose and Motivation

### What Is a Reducer

In LangGraph, every field in a graph's state schema has an associated **reducer** -- a function that defines how new values written by nodes merge with the existing value of that field. When a node returns `{"messages": [some_message]}`, the reducer for the `messages` key decides whether that message is appended, replaces an existing message with the same ID, or triggers some other transformation.

Without a reducer, a state field is simply overwritten: the last write wins. With a reducer, the framework can implement accumulation semantics (append to a list), deduplication (replace by ID), deletion (tombstone a message), or any other merge logic the application requires.

### The O(N^2) Problem with Standard add_messages

LangGraph ships a built-in reducer called `add_messages` that handles the common case: it appends new messages, replaces existing messages when IDs match, and supports `RemoveMessage` sentinels for deletion. However, `add_messages` works with the default `LastValue` channel type, which stores the **full message list** in every checkpoint. For an N-turn conversation with C checkpoints, this produces O(N * C) total storage -- effectively O(N^2) growth:

| Step | Messages stored in checkpoint | Cumulative storage |
|------|------------------------------|--------------------|
| 1    | 1 message                    | 1                  |
| 2    | 2 messages                   | 3                  |
| 3    | 3 messages                   | 6                  |
| N    | N messages                   | N(N+1)/2 = O(N^2)  |

For a Deep Agent session with hundreds of tool calls, each producing multiple messages, this quadratic growth becomes a real storage and performance bottleneck.

### The DeltaChannel Solution

Deep Agents replaces `LastValue` with `DeltaChannel`. A `DeltaChannel` stores only the *writes* (deltas) at each step rather than the full accumulated value. The reducer is called at read time to reconstruct the current state from the base snapshot plus all accumulated deltas. This brings checkpoint storage down to **O(N)** -- each message is stored once.

The tradeoff is that reading the state requires replaying deltas since the last snapshot. The `snapshot_frequency=50` parameter creates periodic full snapshots to bound the replay cost: at most 50 steps of deltas must be replayed to reconstruct the current messages list.

### Why a Custom Reducer (Not the Upstream One)

The module docstring explains the design rationale:

> Adapted from langgraph's `_messages_delta_reducer` (PR #7729). The upstream version coerces `BaseMessageChunk` writes to full messages for parity with `add_messages`. Deepagents never writes chunks to the messages channel -- `langchain.agents.create_agent` appends full `AIMessage` objects, and streaming via `astream_events` operates on the output side, not the state side -- so we skip the per-message coercion.

Two deliberate omissions from the upstream version:

1. **No chunk coercion.** Deep Agents never writes `BaseMessageChunk` objects to the messages channel. Skipping the coercion saves per-message overhead on every reducer call.

2. **No ID assignment.** LangGraph's `ensure_message_ids` hook stamps stable UUIDs onto all `BaseMessage` writes before they are serialized to the checkpoint. By the time the reducer sees a message, it already has a stable ID. Assigning IDs in the reducer would be redundant and, critically, **fragile** -- a reducer runs on replay too, where a randomly-assigned ID would differ from the one stored in the checkpoint, breaking dedup and causing duplicate messages.

From the module docstring:

> ID assignment is intentionally absent here. LangGraph's `ensure_message_ids` stamps stable UUIDs onto all `BaseMessage` writes before they are serialised to the checkpoint, so by the time the reducer sees a message it already has a stable ID. Assigning IDs in the reducer would be both redundant and fragile (a reducer runs on replay too, where a randomly-assigned ID would differ from the one stored in the checkpoint).

---

## 2. Key Dependencies

```python
from langchain_core.messages import (
    AnyMessage,
    BaseMessage,
    RemoveMessage,
    convert_to_messages,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES
```

| Import | Package | Role |
|--------|---------|------|
| `AnyMessage` | `langchain_core.messages` | Union type covering all message variants |
| `BaseMessage` | `langchain_core.messages` | Concrete base class for typed messages (`HumanMessage`, `AIMessage`, etc.) |
| `RemoveMessage` | `langchain_core.messages` | Tombstone sentinel: "delete the message with this ID" |
| `convert_to_messages` | `langchain_core.messages` | Coerces raw dicts, strings, and tuples to `BaseMessage` instances |
| `REMOVE_ALL_MESSAGES` | `langgraph.graph.message` | Special ID constant: "wipe the entire message list" |

---

## 3. Function Signature

```python
def _messages_delta_reducer(  # noqa: C901, PLR0912
    state: list[AnyMessage] | None,
    writes: list[list[AnyMessage]],
) -> list[AnyMessage]:
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `state` | `list[AnyMessage] \| None` | The current accumulated messages from the checkpoint. `None` when `DeltaChannel.replay_writes` encounters a thread whose earliest checkpoint did not seed `messages: []`. |
| `writes` | `list[list[AnyMessage]]` | Batched writes from one or more graph nodes in the current step. Each write is typically a `list`, but single message-likes are also accepted and wrapped. |

**Returns:** `list[AnyMessage]` -- the new, deduplicated, tombstone-free message list.

This is a **batch reducer**. Unlike a standard LangGraph reducer that receives `(state, single_write)` and is called once per write, a `DeltaChannel` reducer receives **all writes at once** in the `writes` parameter and is called once per read. Each element of `writes` is itself a list of message-likes (or occasionally a single message-like that gets wrapped).

The function is marked `noqa: C901, PLR0912` to suppress complexity warnings -- the logic is intentionally consolidated into a single function for readability and performance rather than split across helpers.

---

## 4. The REMOVE_ALL_MESSAGES Sentinel

```python
from langgraph.graph.message import REMOVE_ALL_MESSAGES
```

`REMOVE_ALL_MESSAGES` is a constant imported from LangGraph (defined at line 31 of the source file's import). It is used as the `id` field of a `RemoveMessage` to signal a complete conversation reset. When the reducer encounters `RemoveMessage(id=REMOVE_ALL_MESSAGES)` in the writes:

1. The entire accumulated state is cleared.
2. All writes before and including the sentinel are discarded.
3. Only writes after the last sentinel survive.

This mechanism is used by the summarization middleware. When the conversation grows too long and is summarized, a `RemoveMessage(id=REMOVE_ALL_MESSAGES)` clears the history, and the summary is written as the new starting point.

Usage example:

```python
from langchain_core.messages import RemoveMessage, HumanMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

# Clear everything and start fresh with a summary
return {"messages": [
    RemoveMessage(id=REMOVE_ALL_MESSAGES),
    HumanMessage(content="[Summary of previous conversation]", id="summary-1"),
]}
```

---

## 5. Algorithm: Line-by-Line Walkthrough

### Phase 1 -- Flatten writes (lines 46-51)

```python
# Each write is either a list of message-likes or a single message-like
# (BaseMessage / dict / str / tuple). Only lists flatten; everything
# else is one message.
flat: list[Any] = []
for w in writes:
    if isinstance(w, list):
        flat.extend(w)
    else:
        flat.append(w)
```

The `writes` parameter is `list[list[AnyMessage]]`, but each inner element may also be a single message-like (a `BaseMessage`, a dict, a string, or a tuple). Lists are flattened; scalars are wrapped. After this phase, `flat` is a single-level list of raw message-likes.

### Phase 2 -- Coerce to typed messages (lines 54-59)

```python
# Steady state: the reducer's own output is already typed BaseMessages,
# so skip convert_to_messages on the fast path. Only raw input (initial
# dicts, deserialized blobs) hits the slow path. `state` is `None` on
# `DeltaChannel.replay_writes` for threads whose earliest checkpoint did
# not seed `messages: []`; treat that as the empty list so the slow path
# doesn't pass `None` into `convert_to_messages`.
state_msgs = state if state and isinstance(state[0], BaseMessage) else cast("list[AnyMessage]", convert_to_messages(state or []))
msgs = cast("list[AnyMessage]", convert_to_messages(flat))
```

Two coercion paths:

- **State (fast path).** If `state` is already a list of `BaseMessage` objects (the normal steady-state case), skip `convert_to_messages` entirely. The check `state and isinstance(state[0], BaseMessage)` short-circuits conversion when the first element is already a `BaseMessage`. This avoids iterating the full state list on every step just to check types.

- **State (slow path / None handling).** If `state` is `None` (happens during `DeltaChannel.replay_writes` for threads whose earliest checkpoint did not seed `messages: []`) or if state contains raw types (initial HTTP-driven invocation), coerce via `convert_to_messages`. The `state or []` guard converts `None` to `[]` to prevent passing `None` into `convert_to_messages`, which would raise.

- **Writes (always coerced).** The incoming writes are always run through `convert_to_messages` because new writes may arrive as raw dicts from an API layer (e.g., `{"role": "user", "content": "hello"}`), strings, or tuples.

### Phase 3 -- REMOVE_ALL_MESSAGES sentinel scan (lines 62-69)

```python
# REMOVE_ALL_MESSAGES resets everything; find the last sentinel and
# discard all state plus all writes before it.
remove_all_idx = None
for idx, m in enumerate(msgs):
    if isinstance(m, RemoveMessage) and m.id == REMOVE_ALL_MESSAGES:
        remove_all_idx = idx
if remove_all_idx is not None:
    state_msgs = []
    msgs = msgs[remove_all_idx + 1:]
```

The loop scans **all** incoming messages to find the **last** `REMOVE_ALL_MESSAGES` sentinel. The scan does not break early -- `remove_all_idx` is overwritten on each match, so if multiple sentinels appear in a single write batch, only the final one takes effect. Everything before it (including earlier resets and any messages between resets) would be wiped anyway.

When found:
- `state_msgs` is reset to `[]` -- the entire conversation history is discarded.
- `msgs` is sliced to include only messages **after** the last sentinel.

### Phase 4 -- Build result list with ID-based deduplication (lines 71-89)

```python
result: list[AnyMessage | None] = []
index: dict[str, int] = {}

# Step A: seed with existing state
for m in state_msgs:
    if m.id is not None:
        index[m.id] = len(result)
    result.append(m)

# Step B: merge incoming messages
for msg in msgs:
    mid = msg.id
    if mid is None:
        result.append(msg)              # (a) no ID -> always append
    elif isinstance(msg, RemoveMessage):
        if mid in index:
            result[index[mid]] = None   # (b) tombstone -> null out
            del index[mid]
    elif mid in index:
        result[index[mid]] = msg        # (c) ID collision -> overwrite in-place
    else:
        index[mid] = len(result)
        result.append(msg)              # (d) new ID -> append
```

The `index` dict maps message IDs to their position in `result`. This provides O(1) lookup for ID collisions and tombstone removal.

Four cases for each incoming message:

| Case | Condition | Action |
|------|-----------|--------|
| (a) | `mid is None` | Append unconditionally. No dedup possible. |
| (b) | `isinstance(msg, RemoveMessage)` and `mid in index` | Set `result[pos]` to `None`, delete from index. |
| (c) | `mid in index` (non-remove) | Overwrite `result[pos]` with new message. Same position preserved. |
| (d) | `mid not in index` (non-remove) | Append to end, record in index. |

Note that a `RemoveMessage` whose target ID is **not** in the index is silently ignored -- it does not raise. This is intentional: the message may have already been removed by a previous step or by `REMOVE_ALL_MESSAGES`.

### Phase 5 -- Filter out tombstoned entries (line 90)

```python
return [m for m in result if m is not None]
```

A simple list comprehension strips out the `None` holes left by tombstone removal. The result is a clean, gap-free list of live messages.

---

## 6. Message Operations: Dedup, Tombstoning, and Reset

The reducer supports four distinct operations on the message list:

### Append (New Messages)

Any message whose ID is not already present in the state (or whose ID is `None`) is appended to the end of the list. This is the default operation for new human messages, AI responses, and tool results.

```
State:  [HumanMessage(id="h1", content="hello")]
Write:  [AIMessage(id="a1", content="Hello!")]
Result: [HumanMessage(id="h1", content="hello"), AIMessage(id="a1", content="Hello!")]
```

### Dedup / Replace (Update by ID)

When a write contains a message whose ID matches an existing message in the state, the new message **replaces** the old one at the same position. This is an in-place update, not an append-then-dedup. The position in the conversation is preserved -- only the content changes.

```
State:  [HumanMessage(id="h1", content="old")]
Write:  [HumanMessage(id="h1", content="new")]
Result: [HumanMessage(id="h1", content="new")]
```

This is useful for middleware that needs to modify a previous message (e.g., redacting content, updating metadata) without changing the conversation order.

### Tombstoning (Delete by ID)

A `RemoveMessage` sentinel with a specific message ID removes that message from the conversation. The message is tombstoned (set to `None` in the result array) and filtered out in the final compaction step.

```
State:  [HumanMessage(id="h1"), AIMessage(id="a1"), AIMessage(id="a2")]
Write:  [RemoveMessage(id="a1")]
Result: [HumanMessage(id="h1"), AIMessage(id="a2")]
```

If the target ID does not exist in the current state, the `RemoveMessage` is silently ignored -- no error is raised.

### Reset (REMOVE_ALL_MESSAGES)

A `RemoveMessage` with `id=REMOVE_ALL_MESSAGES` clears the entire conversation history. Any messages written after the sentinel in the same batch become the new conversation.

```
State:  [HumanMessage(id="h1"), AIMessage(id="a1")]
Write:  [RemoveMessage(id=REMOVE_ALL_MESSAGES), HumanMessage(id="h2", content="fresh start")]
Result: [HumanMessage(id="h2", content="fresh start")]
```

---

## 7. Differences from Upstream LangGraph add_messages

| Aspect | Upstream `add_messages` | Deep Agents `_messages_delta_reducer` |
|--------|------------------------|---------------------------------------|
| **Channel type** | LastValue (full state at every checkpoint) | DeltaChannel (only deltas stored per step) |
| **Storage complexity** | O(N^2) across N steps | O(N) across N steps |
| **Reducer call pattern** | `(state, single_write)` -- called once per write | `(state, list[writes])` -- called once with all writes (batch) |
| **Chunk coercion** | Coerces `BaseMessageChunk` to full messages | Skipped -- Deep Agents never writes chunks to the messages channel |
| **ID assignment** | Assigns UUIDs to messages with `id=None` | No ID assignment -- relies on LangGraph's `ensure_message_ids` hook |
| **REMOVE_ALL_MESSAGES** | Supported | Supported (identical semantics) |
| **Dedup by ID** | Supported | Supported (identical semantics) |
| **RemoveMessage tombstoning** | Supported | Supported (identical semantics) |
| **None state handling** | Not applicable (LastValue always has a base) | Explicitly handled -- `None` treated as empty list |
| **Raw input coercion** | Via `convert_to_messages` | Via `convert_to_messages` (with fast-path skip for typed state) |

### Why No ID Assignment in the Reducer

This is the most critical design difference. The correctness argument: `DeltaChannel` replays deltas through the reducer when reconstructing state. If the reducer assigned random UUIDs during the initial write, those UUIDs would be serialized into the checkpoint. On replay, the reducer would assign *different* random UUIDs, breaking dedup and causing duplicate messages. By relying on `ensure_message_ids` (which runs once, before serialization), the IDs are stable across replays.

### Why No Chunk Coercion

Deep Agents' architecture keeps streaming on the output side (`astream_events`). The `create_agent` function appends full `AIMessage` objects, not `BaseMessageChunk` fragments. Chunks never reach the state channel, so the coercion step can be safely omitted for better performance.

---

## 8. Integration with DeltaChannel and snapshot_frequency

### DeepAgentState Declaration

The reducer is wired into the agent's state schema through `DeepAgentState`, defined in `libs/deepagents/deepagents/graph.py` (lines 64-67):

```python
from langgraph.channels.delta import DeltaChannel
from deepagents._messages_reducer import _messages_delta_reducer


class DeepAgentState(AgentState):
    """AgentState with DeltaChannel on messages to reduce
    checkpoint growth from O(N^2) to O(N)."""

    messages: Required[Annotated[
        list[AnyMessage],
        DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)
    ]]
```

Three components work together:

1. **`DeltaChannel`** -- The LangGraph channel type that stores deltas between checkpoints instead of full snapshots. It calls the reducer with `(state, writes)` on each read and manages the snapshot/delta lifecycle.

2. **`_messages_delta_reducer`** -- The reducer function documented in this file. It receives the current state and batched writes, and returns the new merged message list.

3. **`snapshot_frequency=50`** -- A full snapshot of the message list is stored every 50 Pregel steps. Between snapshots, only the deltas (new writes) are persisted.

### DeltaChannel Mechanics

A `DeltaChannel` works differently from a `LastValue` channel:

1. **On write**: Only the delta (the new messages from this step) is serialized to the checkpoint. The full accumulated list is not stored.

2. **On read**: The channel calls `reducer(base_snapshot, [delta_1, delta_2, ..., delta_n])` to reconstruct the current value from the last snapshot plus all deltas since that snapshot.

3. **Snapshots**: Every `snapshot_frequency` steps (50 in Deep Agents), the channel stores a full snapshot of the accumulated value. This bounds the replay cost: at most 50 deltas must be replayed to reconstruct the current state.

### snapshot_frequency=50 Tuning

The value 50 is a tuning parameter that balances two costs:

- **Lower values** (more frequent snapshots): Faster reads (fewer deltas to replay), but more storage (snapshots are large for long conversations).
- **Higher values** (less frequent snapshots): Less storage, but slower reads when many deltas must be replayed.

For a typical agent conversation, 50 Pregel steps between snapshots means the reducer replays at most 50 steps of message writes to reconstruct the current list. Given that each step typically adds 1-3 messages, this means replaying approximately 50-150 messages at worst.

### How create_deep_agent Wires It In

The `create_deep_agent` factory function uses `DeepAgentState` as the default state schema (line 856 of `graph.py`):

```python
state_schema=state_schema if state_schema is not None else DeepAgentState,
```

Every Deep Agent created through the standard factory function automatically gets the delta-channel-backed messages reducer. There is no additional configuration required.

### Extending DeepAgentState

Users can extend `DeepAgentState` with custom fields. The `messages` channel definition (including the `DeltaChannel` and reducer) is inherited automatically:

```python
from deepagents.graph import DeepAgentState, create_deep_agent


class MyState(DeepAgentState):
    page_url: str
    file_urls: list[str]


agent = create_deep_agent(model=..., state_schema=MyState)
```

The `state_schema` parameter on `create_deep_agent` must be a `TypedDict` subclass of `DeepAgentState`. This constraint ensures the `DeltaChannel` reducer on `messages` is always present. Because `TypedDict` subclasses do not support `issubclass` checks at runtime, this constraint is enforced by typing alone and not validated at runtime (lines 544-546 of `graph.py`).

### Interaction with Overwrite

The filesystem middleware (`libs/deepagents/deepagents/middleware/filesystem.py`) notes an important interaction:

> When a new eviction fires, uses `Overwrite` to atomically replace the messages channel with a fully-identified list. A plain append of the tagged message would not survive `DeltaChannel` replay: the original `HumanMessage(id=None)` write gets a fresh UUID on replay that doesn't match the eviction Command's ID, producing a duplicate.

Operations that need to rewrite the full messages list (like context window eviction) must use `Overwrite` rather than appending, because `DeltaChannel` replay can produce different IDs for `id=None` messages on each replay. This is a direct consequence of the reducer not assigning IDs -- `ensure_message_ids` runs once before serialization, but on replay the delta is replayed as-is without re-running the hook.

### Import Path

The reducer is a private module (`_messages_reducer.py`, note the leading underscore) and is not part of the public API. It is imported only by `graph.py`:

```python
from deepagents._messages_reducer import _messages_delta_reducer
```

Users should not import or call the reducer directly. The correct way to interact with the message list is through standard LangGraph state writes -- returning `{"messages": [...]}` from a node -- and the reducer handles the merge automatically.

---

## 9. Tool Message Handling

The reducer itself does not contain special logic for tool messages -- it treats `ToolMessage`, `AIMessage`, `HumanMessage`, and all other message types uniformly through the ID-based merge algorithm. However, the ID-based operations have important implications for tool message consistency.

### The Orphaned Tool Message Problem

In LangGraph agent loops, tool calls and tool results form paired structures:

1. An `AIMessage` contains one or more `tool_calls` entries in its metadata.
2. A `ToolMessage` with a matching `tool_call_id` contains the result of executing that tool call.

If the `AIMessage` containing tool calls is removed (via `RemoveMessage`) but the corresponding `ToolMessage` results remain, the tool messages become **orphaned** -- they reference a tool call that no longer exists in the conversation. Many LLM providers reject conversations with orphaned tool messages because they violate the expected request/response structure.

### Design Decision: No Automatic Cleanup

The reducer does not automatically detect or resolve orphaned tool messages. This is by design -- the reducer operates at the message-list level and does not inspect message content or metadata. It has no knowledge of which `ToolMessage` corresponds to which `AIMessage`.

Callers that remove AI messages containing tool calls are responsible for also removing the corresponding tool messages. In practice, this is handled at a higher level:

- The **summarization middleware**, which is the primary consumer of `RemoveMessage` and `REMOVE_ALL_MESSAGES`, uses bulk eviction (`REMOVE_ALL_MESSAGES`) rather than selective removal, which eliminates the orphan problem entirely by clearing all messages and replacing them with a summary.
- Any middleware or node that performs selective message removal must track the tool-call-to-tool-result relationship itself.

---

## 10. Edge Cases

### 10.1 None Base State (Issue #3564)

When `DeltaChannel` replays writes for a thread whose earliest checkpoint did not seed `messages: []`, it passes `state=None`. The reducer treats this identically to an empty list:

```python
state_msgs = (
    state
    if state and isinstance(state[0], BaseMessage)
    else cast("list[AnyMessage]", convert_to_messages(state or []))
)
```

The `state or []` expression converts `None` to `[]` before passing it to `convert_to_messages`. This was a regression fix for [issue #3564](https://github.com/langchain-ai/deepagents/issues/3564).

Three sub-cases are tested:
1. `None` state with actual writes -- must produce the writes.
2. `None` state with empty `writes` list -- must produce `[]`.
3. `None` state with `[[]]` (empty inner write) -- must produce `[]`.

### 10.2 Empty Write Batches

Empty write batches (`[[]]` or `[]`) are handled naturally. The flatten step produces an empty `flat` list, `convert_to_messages([])` returns `[]`, and the merge phase has nothing to iterate over. The existing state is returned unchanged.

### 10.3 Messages Without IDs

Messages with `id=None` are always appended and never deduplicated or replaced. They cannot be targeted by `RemoveMessage` because there is no ID to match against. In practice, this case is uncommon -- LangGraph's `ensure_message_ids` hook assigns stable UUIDs to all messages before they reach the reducer. The `id=None` path exists as a safety net for edge cases where messages bypass the ID assignment hook.

### 10.4 Duplicate IDs in Writes

If multiple messages in the same write batch share the same ID, the last one wins. The merge loop processes messages sequentially: the first message with a given ID is appended and indexed, and subsequent messages with the same ID replace it at the same position. This is consistent with last-write-wins semantics.

### 10.5 Duplicate IDs Across State and Writes

When a write contains a message whose ID already exists in the state, the write replaces the state message. The new message occupies the same position in the result list as the original, preserving conversation order.

### 10.6 System Message Handling

The reducer does not treat system messages specially. `SystemMessage` objects are indexed, merged, replaced, and deleted by the same ID-based logic as all other message types. The system prompt is typically assembled outside the reducer (in `create_deep_agent`'s prompt assembly logic) and prepended to the message list at model-call time, not stored as a persistent message in the state.

### 10.7 Raw Input Coercion

The reducer accepts raw dicts, strings, and tuples as input (not just typed `BaseMessage` objects). These are coerced to typed messages via `convert_to_messages` before processing:

```python
# All of these are valid inputs to the reducer via graph writes:
{"role": "user", "content": "hello"}       # dict
("user", "hello")                           # tuple
"hello"                                     # string
HumanMessage(content="hello")               # BaseMessage
```

---

## 11. Performance Characteristics

### Time Complexity

| Phase | Complexity | Notes |
|-------|-----------|-------|
| Flatten writes | O(W) | W = total messages across all writes |
| `convert_to_messages` (state fast path) | O(1) | Single `isinstance` check on `state[0]` |
| `convert_to_messages` (state slow path) | O(S) | S = state length; only on first invocation or raw dicts |
| `convert_to_messages` (writes) | O(W) | Always runs on incoming writes |
| REMOVE_ALL_MESSAGES scan | O(W) | Linear scan of writes only, not state |
| Build index from state | O(S) | Dict insertion is amortised O(1) |
| Merge incoming messages | O(W) | Dict lookup/insert is amortised O(1) |
| Filter None entries | O(S + W) | Single pass over result list |
| **Total** | **O(S + W)** | Linear in the combined size of state + writes |

### Space Complexity

- **`index` dict:** O(S + W) entries (one per unique ID).
- **`result` list:** O(S + W) entries (includes `None` holes before filtering).
- **Final output:** O(S + W) minus tombstoned entries.

### The Fast Path Optimisation

The `isinstance(state[0], BaseMessage)` check is critical for steady-state performance. After the first invocation, the reducer's own output is always a list of typed `BaseMessage` objects. Without this check, every step would call `convert_to_messages` on the entire accumulated state, which involves per-element type checking and potentially constructor calls.

In a 100-turn conversation with an average of 2 messages per turn (one human, one AI), the state list has ~200 messages. The fast path saves 200 calls to `convert_to_messages`'s inner loop on every single step.

### In-Place Overwrite vs. Append-and-Deduplicate

The reducer uses positional overwrite (`result[index[mid]] = msg`) rather than building a new list and deduplicating at the end. This preserves message ordering: an updated message stays at its original position in the conversation, not moved to the end. This is semantically important for chat UIs that display messages in order.

---

## 12. Test Coverage

The test suite (`libs/deepagents/tests/unit_tests/test_messages_reducer.py`) exercises both the reducer function directly and the full end-to-end checkpoint round-trip.

### Test Graph Setup

Tests construct a minimal `StateGraph` with the same `DeltaChannel` configuration used in production:

```python
State = TypedDict(
    "State",
    {"messages": Annotated[list, DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)]},
)
```

### Individual Tests

| Test | What it validates |
|------|-------------------|
| `test_get_state_messages_have_ids` | Every message from `get_state()` has a non-`None` ID after a round-trip through the checkpoint |
| `test_dict_style_invoke_messages_have_stable_ids` | Raw dict-style input (`{"role": "user", "content": "..."}`) yields stable IDs after coercion; IDs are identical across repeated `get_state()` calls |
| `test_human_message_id_stable_across_invocations_sync` | A `HumanMessage` retains its ID when a thread is resumed across multiple `invoke()` calls (sync path). Key regression test for LangGraph issue #7913. |
| `test_human_message_id_stable_across_invocations_async` | Same stability check via `ainvoke` / `aget_state` (async Pregel loop path) |
| `test_reducer_handles_none_base_state` | `state=None` is handled gracefully: single message, empty writes `[]`, and empty batch `[[]]` all work (regression test for [#3564](https://github.com/langchain-ai/deepagents/issues/3564)) |
| `test_reducer_handles_none_base_state_with_dict_messages` | `None` base state combined with raw dict writes correctly coerces to typed `HumanMessage` |

### ID Stability Test (Key Regression)

The most important test verifies that message IDs are stable across thread resumption:

```python
def test_human_message_id_stable_across_invocations_sync() -> None:
    # Turn 1
    graph.invoke({"messages": [HumanMessage(content="write a hello world script")]}, config)
    id_turn1 = next(m.id for m in graph.get_state(config).values["messages"]
                    if isinstance(m, HumanMessage))

    # Turn 2 (resume)
    graph.invoke({"messages": [HumanMessage(content="add error handling")]}, config)
    id_turn2 = next(m.id for m in graph.get_state(config).values["messages"]
                    if isinstance(m, HumanMessage) and m.content == "write a hello world script")

    assert id_turn1 == id_turn2
```

If the reducer were assigning IDs itself (rather than relying on `ensure_message_ids`), the replayed state would get different random IDs, and this assertion would fail.

---

## 13. Common Pitfalls and Design Rationale

### Why `RemoveMessage` for a non-existent ID is silently ignored

A `RemoveMessage` targeting an ID that is not in the index could mean:
1. The message was already removed by a previous step.
2. The message was cleared by `REMOVE_ALL_MESSAGES`.
3. The `RemoveMessage` was emitted speculatively by a node that did not know whether the message existed.

Raising an error in any of these cases would make the graph brittle. Silent no-op is the safe default.

### Why `id=None` messages are always appended

Some messages (e.g., system messages injected by middleware) may not have IDs. These cannot be deduplicated or tombstoned -- they are always appended. This means repeated injections of the same system message will create duplicates. Callers should assign IDs to any message that may appear more than once.

### Why the sentinel scan finds the last occurrence

If a write batch contains `[REMOVE_ALL, msg_A, REMOVE_ALL, msg_B]`, the correct result is `[msg_B]`, not `[msg_A, msg_B]`. Scanning for the last sentinel ensures all earlier content (including messages between sentinels) is discarded.

---

## 14. What Would Break If You Changed This

| Change | Consequence |
|--------|-------------|
| Assign IDs in the reducer | Replay produces different IDs than the checkpoint; `get_state()` returns unstable IDs; `RemoveMessage` targeting breaks |
| Use a set for dedup instead of positional overwrite | Message order changes when an existing message is updated; chat UI displays messages out of order |
| Coerce `BaseMessageChunk` to full messages | Unnecessary overhead; Deep Agents never writes chunks to state |
| Remove the `state or []` guard | `TypeError` on `DeltaChannel.replay_writes` for threads without initial `messages: []` seeding (issue #3564) |
| Raise on `RemoveMessage` for unknown ID | Graph crashes when a node speculatively removes or when `REMOVE_ALL_MESSAGES` precedes individual removes |
| Use first `REMOVE_ALL_MESSAGES` instead of last | Messages between multiple sentinels in one batch leak through |
| Remove `convert_to_messages` on writes | Dict-style API input crashes the graph with `AttributeError` on `msg.id` access |

---

## 15. Knowledge Check

**Q1.** What happens when `_messages_delta_reducer` receives `state=None` and `writes=[[{"role": "user", "content": "hello"}]]`?

<details><summary>Answer</summary>

The `state or []` guard converts `None` to `[]`. The fast-path check fails (empty list has no `[0]`), so `convert_to_messages([])` returns `[]`. The dict in writes is coerced to a `HumanMessage` via `convert_to_messages`. The result is a single-element list containing that `HumanMessage`. This covers both the None-state edge case (issue #3564) and the dict-coercion path.

</details>

**Q2.** A write batch contains three messages: `[msg_A(id="x"), RemoveMessage(id="x"), msg_B(id="x")]`. What is the final state (assuming empty initial state)?

<details><summary>Answer</summary>

Processing order:
1. `msg_A(id="x")` -- case (d): appended, `index["x"] = 0`.
2. `RemoveMessage(id="x")` -- case (b): `result[0] = None`, `del index["x"]`.
3. `msg_B(id="x")` -- case (d) again (ID no longer in index): appended at position 1, `index["x"] = 1`.

After filtering: `[msg_B]`. The remove tombstoned `msg_A`, and `msg_B` was treated as a new message.

</details>

**Q3.** Why does the reducer check `isinstance(state[0], BaseMessage)` instead of iterating the full state list?

<details><summary>Answer</summary>

Performance optimisation. In steady state, the reducer's own output is always a homogeneous list of `BaseMessage` objects. Checking only the first element is sufficient to determine whether the entire list needs coercion. Iterating the full list would add O(S) overhead on every step for no benefit, since a mixed list (some `BaseMessage`, some raw dicts) does not occur in practice.

</details>

**Q4.** If two nodes in the same graph step both write `RemoveMessage(id=REMOVE_ALL_MESSAGES)`, what happens?

<details><summary>Answer</summary>

Both writes are flattened into `msgs`. The sentinel scan finds the last occurrence. All state and all writes before the last sentinel are discarded. Only writes after the last sentinel survive. The result is identical to a single `REMOVE_ALL_MESSAGES` at the later position -- the earlier one is redundant.

</details>

**Q5.** A `RemoveMessage(id="unknown-999")` is written to a state that does not contain a message with that ID. Does the reducer raise an error?

<details><summary>Answer</summary>

No. The `elif isinstance(msg, RemoveMessage)` branch only acts when `mid in index`. If the ID is not in the index, the message falls through all branches without being appended (since `mid is not None` and it is a `RemoveMessage`). It is silently ignored. This is intentional to avoid brittle error handling in speculative removal scenarios.

</details>

---

## Summary

The messages reducer (`_messages_delta_reducer`) is a compact but critical piece of the Deep Agents runtime. It provides the merge semantics for the conversation history -- append, replace (dedup by ID), delete (tombstone via `RemoveMessage`), and reset (`REMOVE_ALL_MESSAGES`) -- while supporting `DeltaChannel`'s delta-based checkpointing for O(N) storage growth instead of the O(N^2) growth that comes with storing the full message list in every checkpoint.

The reducer intentionally omits chunk coercion (not needed because Deep Agents never writes message chunks to state) and ID assignment (handled upstream by `ensure_message_ids` for replay safety). It handles raw input coercion for HTTP-driven graphs, `None` base states for fresh threads, and the `REMOVE_ALL_MESSAGES` bulk-eviction sentinel used by the summarization middleware.

The reducer is wired into `DeepAgentState` as a private implementation detail (`_messages_reducer.py`) and operates transparently behind standard LangGraph state writes. Users interact with it only indirectly -- by returning `{"messages": [...]}` from graph nodes.

---

*Next: [Chapter 10 -- The Backend System](10_backends.md)*
