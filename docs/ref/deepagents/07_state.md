# Agent State Management in Deep Agents

Every Deep Agents instance is a LangGraph `CompiledStateGraph`, and
every `CompiledStateGraph` has a typed state dictionary that flows
through its nodes, edges, and tools. This document covers the agent
state in depth: the `DeepAgentState` TypedDict, the custom messages
reducer, the `StateBackend`, private state fields, file format versions,
and the mechanisms by which state is read and written during graph
execution.

---

## Table of Contents

1. [DeepAgentState TypedDict](#deepagentstate-typeddict)
2. [The Messages Field and DeltaChannel](#the-messages-field-and-deltachannel)
3. [The _messages_delta_reducer in Detail](#the-_messages_delta_reducer-in-detail)
4. [StateBackend: Ephemeral File Storage in Agent State](#statebackend-ephemeral-file-storage-in-agent-state)
5. [State Access via CONFIG_KEY_READ and CONFIG_KEY_SEND](#state-access-via-config_key_read-and-config_key_send)
6. [File Format Versions](#file-format-versions)
7. [StateBackend Methods](#statebackend-methods)
8. [Private State Fields](#private-state-fields)
9. [State Flow Through the Graph](#state-flow-through-the-graph)
10. [State Components Summary](#state-components-summary)
11. [Checkpointing and DeltaChannel Interaction](#checkpointing-and-deltachannel-interaction)

---

## DeepAgentState TypedDict

Defined in `libs/deepagents/deepagents/graph.py`:

```python
class DeepAgentState(AgentState):
    """AgentState with DeltaChannel on messages to reduce checkpoint
    growth from O(N^2) to O(N)."""

    messages: Required[Annotated[
        list[AnyMessage],
        DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)
    ]]
```

`DeepAgentState` extends LangChain's `AgentState` (itself a
`TypedDict`) with a single field override: the `messages` field is
annotated with a `DeltaChannel` wrapper instead of the standard
`add_messages` reducer.

### Why This Matters

LangChain's default `AgentState` uses the `add_messages` reducer on
the `messages` field. This reducer stores the full messages list at
every checkpoint, leading to O(N^2) total storage growth over a
conversation with N messages.

`DeepAgentState` replaces this with `DeltaChannel`, which stores only
the new or changed messages (the "delta") at each checkpoint. The
full messages list is reconstructed on replay by applying the reducer
over all accumulated deltas from the nearest snapshot forward.

### The `Required` and `Annotated` Wrappers

- `Required` (from `typing`) signals that the `messages` field must
  be present in every state dictionary. This is a TypedDict-level
  annotation.

- `Annotated` (from `typing`) carries the `DeltaChannel` metadata
  that LangGraph uses to determine how to manage the channel.

### Custom State Schemas

Users can extend `DeepAgentState` with additional fields:

```python
class MyState(DeepAgentState):
    page_url: str
    file_urls: list[str]
```

The `state_schema` parameter of `create_deep_agent()` accepts such
subclasses. The constraint that the schema must extend
`DeepAgentState` is enforced by typing only -- Python's `TypedDict`
does not support `issubclass()`, so no runtime validation occurs.

When a custom schema is provided, it is used as the base graph schema
and forwarded to declarative subagent compilation so that subagents
see the same custom fields as the parent agent.

---

## The Messages Field and DeltaChannel

### DeltaChannel Configuration

```python
DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)
```

Two arguments configure the channel:

1. **`_messages_delta_reducer`** -- the reducer function that
   combines accumulated state with new writes. This function handles
   deduplication, removal, and coercion of messages.

2. **`snapshot_frequency=50`** -- a full snapshot of the messages
   list is written to the checkpoint every 50 steps. This bounds
   the maximum replay cost to at most 49 delta replays from the
   nearest snapshot.

### How DeltaChannel Works

In a standard LangGraph channel, the checkpoint stores the full
value of the channel after every step. With DeltaChannel:

1. At each step, only the new writes (deltas) are stored in the
   checkpoint.
2. Every `snapshot_frequency` steps, a full snapshot replaces the
   accumulated deltas.
3. On replay, the system loads the nearest snapshot and applies the
   reducer over subsequent deltas to reconstruct the current state.

This reduces per-checkpoint storage from the full messages list to
only the messages added in that step, transforming total storage
from O(N^2) to O(N).

### Trade-offs

- **Replay cost**: Reconstructing state requires replaying up to
  `snapshot_frequency - 1` deltas from the nearest snapshot. With
  `snapshot_frequency=50`, this means up to 49 reducer calls on
  replay. This is a manageable cost for the significant storage
  savings.

- **Reducer correctness**: The reducer must be deterministic and
  produce the same output given the same inputs, regardless of
  whether it processes deltas individually or in batch. The
  `_messages_delta_reducer` satisfies this requirement.

---

## The _messages_delta_reducer in Detail

Defined in `libs/deepagents/deepagents/_messages_reducer.py` (91
lines). This is the core function that manages the messages channel
state.

### Function Signature

```python
def _messages_delta_reducer(
    state: list[AnyMessage] | None,
    writes: list[list[AnyMessage]]
) -> list[AnyMessage]:
```

- **`state`**: The current accumulated messages list. Can be `None`
  on `DeltaChannel.replay_writes` for threads whose earliest
  checkpoint did not seed `messages: []`.

- **`writes`**: A list of write batches. Each batch is itself a list
  of message-like objects (or a single message-like object).

- **Returns**: The updated messages list.

### Design Decisions

The module docstring explains several important design decisions:

1. **No BaseMessageChunk coercion**: The upstream LangGraph version
   coerces `BaseMessageChunk` writes to full messages. Deep Agents
   never writes chunks to the messages channel -- `create_agent`
   appends full `AIMessage` objects, and streaming via
   `astream_events` operates on the output side, not the state
   side. So chunk coercion is skipped.

2. **No ID assignment**: LangGraph's `ensure_message_ids` stamps
   stable UUIDs onto all `BaseMessage` writes before they are
   serialized to the checkpoint. By the time the reducer sees a
   message, it already has a stable ID. Assigning IDs in the
   reducer would be redundant and fragile (a reducer runs on replay
   too, where a randomly-assigned ID would differ from the one
   stored in the checkpoint).

### Step-by-Step Processing

#### Step 1: Flatten Writes

```python
flat: list[Any] = []
for w in writes:
    if isinstance(w, list):
        flat.extend(w)
    else:
        flat.append(w)
```

The `writes` parameter is a list of batches. Each batch can be a
list of message-likes or a single message-like. This step flattens
everything into a single list.

#### Step 2: Coerce to BaseMessage

```python
state_msgs = (
    state
    if state and isinstance(state[0], BaseMessage)
    else cast("list[AnyMessage]", convert_to_messages(state or []))
)
msgs = cast("list[AnyMessage]", convert_to_messages(flat))
```

Two fast-path optimizations:

- **State fast path**: If the state is non-empty and the first
  element is already a `BaseMessage`, skip `convert_to_messages`.
  In steady state, the reducer's own output is already typed, so
  this is the common case.

- **State None handling**: If `state` is `None` (can happen on
  `DeltaChannel.replay_writes` for threads without an initial
  `messages: []` seed), treat it as the empty list.

The incoming `flat` writes always go through `convert_to_messages`
to handle raw dicts, strings, and tuples from HTTP-driven graphs.

#### Step 3: Handle REMOVE_ALL_MESSAGES Sentinel

```python
remove_all_idx = None
for idx, m in enumerate(msgs):
    if isinstance(m, RemoveMessage) and m.id == REMOVE_ALL_MESSAGES:
        remove_all_idx = idx
if remove_all_idx is not None:
    state_msgs = []
    msgs = msgs[remove_all_idx + 1:]
```

The `REMOVE_ALL_MESSAGES` sentinel is a special constant imported
from `langgraph.graph.message`. When a `RemoveMessage` with this ID
appears in the writes:

- All accumulated state messages are discarded.
- All writes before and including the sentinel are discarded.
- Only writes after the sentinel survive.

If multiple `REMOVE_ALL_MESSAGES` sentinels appear, the *last* one
wins (the loop finds the last index).

This mechanism allows a complete conversation reset without
destroying the graph.

#### Step 4: Build Result with Deduplication

```python
result: list[AnyMessage | None] = []
index: dict[str, int] = {}
for m in state_msgs:
    if m.id is not None:
        index[m.id] = len(result)
    result.append(m)
```

The existing state messages are copied into the result list, and an
`index` dictionary maps message IDs to their positions. Messages
without IDs (id=None) are appended but not indexed.

#### Step 5: Process New Messages

```python
for msg in msgs:
    mid = msg.id
    if mid is None:
        result.append(msg)
    elif isinstance(msg, RemoveMessage):
        if mid in index:
            result[index[mid]] = None
            del index[mid]
    elif mid in index:
        result[index[mid]] = msg
    else:
        index[mid] = len(result)
        result.append(msg)
```

Four cases for each new message:

1. **No ID (mid is None)**: Append to the end unconditionally. These
   messages cannot be deduplicated or removed.

2. **RemoveMessage with known ID**: Tombstone removal. The message
   at the indexed position is set to `None` and the ID is removed
   from the index. The `None` slots are filtered out in the final
   step.

3. **Known ID, not a RemoveMessage**: In-place update. The message
   at the indexed position is replaced with the new version. This
   handles message updates (e.g., streaming partial messages being
   replaced by complete messages).

4. **Unknown ID, not a RemoveMessage**: New message. The ID is
   indexed and the message is appended.

#### Step 6: Filter Nones

```python
return [m for m in result if m is not None]
```

Tombstoned messages (set to `None` by `RemoveMessage` processing)
are filtered out, producing the final clean messages list.

### Performance Characteristics

- **Time complexity**: O(S + W) where S is the number of state
  messages and W is the number of new write messages. The index
  dictionary provides O(1) lookups for deduplication and removal.

- **Space complexity**: O(S + W) for the result list and index
  dictionary.

- **Batch efficiency**: The reducer processes all writes in a single
  pass, avoiding the overhead of repeated list scans that would
  occur with per-message reduction.

---

## StateBackend: Ephemeral File Storage in Agent State

Defined in `libs/deepagents/deepagents/backends/state.py` (382
lines). `StateBackend` implements the `BackendProtocol` interface and
stores files directly in the LangGraph agent state.

### Characteristics

- **Ephemeral**: Files persist within a conversation thread but not
  across threads.
- **Checkpointed**: State is automatically checkpointed after each
  agent step.
- **No filesystem access**: All operations work on in-memory state
  data, not actual filesystem paths.
- **Default backend**: When `create_deep_agent()` is called without
  a `backend` argument, a `StateBackend()` is created.

### Initialization

```python
class StateBackend(BackendProtocol):
    def __init__(
        self,
        runtime: object = None,
        *,
        file_format: FileFormat = "v2",
    ) -> None:
```

- **`runtime`**: Deprecated since 0.5.0. Accepted for backward
  compatibility but ignored. State is now read/written via
  `get_config()`.

- **`file_format`**: Storage format version. `"v1"` stores content
  as `list[str]` (lines split on `\n`) without an `encoding` field.
  `"v2"` (default) stores content as a plain `str` with an
  `encoding` field.

---

## State Access via CONFIG_KEY_READ and CONFIG_KEY_SEND

`StateBackend` reads and writes state through LangGraph's internal
Pregel channel mechanism, using two configuration keys:

### CONFIG_KEY_READ

Used by `_read_files()` to access the current `files` channel:

```python
def _read_files(self) -> dict[str, Any]:
    config = self._get_config()
    read = config["configurable"][CONFIG_KEY_READ]
    fresh = True
    return read("files", fresh) or {}
```

- The `read` function is a LangGraph Pregel internal that reads a
  channel's current value.
- `fresh=True` applies any pending task writes through the channel's
  reducer before returning, giving **read-your-writes semantics**
  within a single superstep. This means a tool that writes a file
  and then reads it back will see the written content, even within
  the same graph step.

### CONFIG_KEY_SEND

Used by `_send_files_update()` to queue writes to the `files`
channel:

```python
def _send_files_update(self, update: dict[str, Any]) -> None:
    config = self._get_config()
    send = config["configurable"][CONFIG_KEY_SEND]
    send([("files", update)])
```

- The `send` function takes a list of `(channel, value)` tuples.
- The `files` channel uses a dict-merge reducer, so only changed
  files need to be included -- unchanged files are preserved by the
  reducer.
- Sends are visible to subsequent `_read_files` calls within the
  same superstep via the `fresh=True` parameter.
- They are committed to state at the node boundary.

### Why This Architecture

This design allows `StateBackend` to be initialized once and then
used from any graph context (tools, middleware nodes, etc.) without
requiring explicit state passing. The state access goes through the
LangGraph configuration system, which is available via `get_config()`
from any code running inside a graph execution.

### Error Handling

`_get_config()` raises `RuntimeError` in two cases:

1. **Outside graph execution**: When `get_config()` itself raises
   (no active graph context).
2. **Missing Pregel keys**: When `CONFIG_KEY_READ` is not in the
   configurable dictionary.

Both error messages direct users to pass files on invoke instead:
`agent.invoke({"messages": [...], "files": {...}})`.

---

## File Format Versions

`StateBackend` supports two file storage formats, controlled by the
`file_format` parameter.

### v1 (Legacy)

```python
{
    "content": ["line 1", "line 2", "line 3"],  # list[str]
    # No "encoding" field
    "created_at": "2024-01-01T00:00:00Z",
    "modified_at": "2024-01-01T00:00:00Z",
}
```

- Content is stored as a `list[str]`, with each element being one
  line of the file (split on `\n`).
- No `encoding` field is present.
- Size computation joins lines with `\n`: `len("\n".join(raw))`.

### v2 (Current Default)

```python
{
    "content": "line 1\nline 2\nline 3",  # str
    "encoding": "utf-8",  # or "base64"
    "created_at": "2024-01-01T00:00:00Z",
    "modified_at": "2024-01-01T00:00:00Z",
}
```

- Content is stored as a plain `str`.
- `encoding` field is present: `"utf-8"` for text files, `"base64"`
  for binary files.
- Size is simply `len(content)`.

### Backward Compatibility

All `StateBackend` methods handle both formats when reading.
The `_prepare_for_storage` method converts `FileData` to the
appropriate format when writing:

```python
def _prepare_for_storage(self, file_data: FileData) -> dict[str, Any]:
    if self._file_format == "v1":
        return _to_legacy_file_data(file_data)
    return {**file_data}
```

---

## StateBackend Methods

### ls(path: str) -> LsResult

Lists files and directories in the specified directory
(non-recursive).

**Algorithm:**

1. Read all files from state via `_read_files()`.
2. Normalize the path to have a trailing slash.
3. Iterate all file paths:
   - If the file path starts with the normalized directory path:
     - If the relative path (after the directory prefix) contains
       `/`, extract the immediate subdirectory name and add it to
       a `subdirs` set.
     - Otherwise, the file is directly in the current directory.
       Compute its size and add a `FileInfo` entry.
4. Add directory entries from the `subdirs` set.
5. Sort all entries by path.

**Return:** `LsResult` with a list of `FileInfo` dicts, each
containing `path`, `is_dir`, `size`, and `modified_at`.

### read(file_path, offset=0, limit=2000) -> ReadResult

Reads file content for the requested line range.

**Algorithm:**

1. Read files from state.
2. If the file is not found, return `ReadResult(error=...)`.
3. If the file type (determined by extension) is not text (e.g.,
   image, audio, video), return the raw `file_data` without slicing.
4. For text files, call `slice_read_response(file_data, offset,
   limit)` to extract the requested line range.
5. Return a `ReadResult` with the sliced `FileData`, preserving
   `encoding`, `created_at`, and `modified_at` from the original.

**Note:** Line-number formatting is applied by the middleware, not
by the backend. The backend returns raw (unformatted) content.

### write(file_path, content) -> WriteResult

Creates a new file. Returns an error if the file already exists.

**Algorithm:**

1. Read current files to check for existence.
2. If the file already exists, return `WriteResult(error=...)` with
   a message directing the user to read and edit instead.
3. Create a new `FileData` via `create_file_data(content)`.
4. Queue the update via `_send_files_update()`.
5. Return `WriteResult(path=file_path)`.

### edit(file_path, old_string, new_string, replace_all=False) -> EditResult

Edits a file by replacing string occurrences.

**Algorithm:**

1. Read current files and find the target file.
2. If the file is not found, return `EditResult(error=...)`.
3. Convert the file data to a string via `file_data_to_string()`.
4. Call `perform_string_replacement(content, old_string, new_string,
   replace_all)`.
5. If the replacement returns an error string (e.g., `old_string`
   not found or not unique), return `EditResult(error=...)`.
6. Otherwise, update the file data and queue the update.
7. Return `EditResult(path=file_path, occurrences=count)`.

### grep(pattern, path=None, glob=None) -> GrepResult

Searches state files for a literal text pattern.

**Implementation:** Delegates to `grep_matches_from_files()` utility.
The path defaults to `"/"` when not specified. The glob parameter
filters which files are searched.

### glob(pattern, path=None) -> GlobResult

Gets `FileInfo` for files matching a glob pattern.

**Algorithm:**

1. Read files from state.
2. Call `_glob_search_files(files, pattern, path)`.
3. If no files match, return `GlobResult(matches=[])`.
4. Parse the matching paths and build `FileInfo` entries with
   size and `modified_at` for each match.

### upload_files(files: list[tuple[str, bytes]]) -> list[FileUploadResponse]

Uploads multiple files to state.

**Algorithm:**

1. Read existing files.
2. For each `(path, content)` tuple:
   - Try to decode content as UTF-8. On `UnicodeDecodeError`,
     base64-encode the content instead.
   - If the file already exists, update it via `update_file_data()`.
     If not, create it via `create_file_data()`.
   - Add to the batch update dictionary.
3. Send all updates in a single `_send_files_update()` call.
4. Return a `FileUploadResponse` for each file.

Unlike `write()`, `upload_files()` does not error on existing files --
it updates them.

### download_files(paths: list[str]) -> list[FileDownloadResponse]

Downloads multiple files from state.

**Algorithm:**

1. Read files from state.
2. For each requested path:
   - If the file is not found, return a response with
     `error="file_not_found"`.
   - Convert file data to a string via `file_data_to_string()`.
   - Encode the content: UTF-8 text is encoded to bytes via
     `.encode("utf-8")`; base64-encoded content is decoded via
     `base64.standard_b64decode()`.
3. Return a `FileDownloadResponse` for each path.

---

## Private State Fields

Defined in `libs/deepagents/deepagents/middleware/_state.py` (30
lines).

### Purpose

Some middleware adds fields to the agent state schema that should not
be visible to subagents. Fields annotated with `PrivateStateAttr`
(from `langchain.agents.middleware.types`) are "private" -- they
should not leak from the parent agent's state to child subagents.

### private_state_field_names()

```python
def private_state_field_names(
    *state_schemas: type[object]
) -> frozenset[str]:
```

This function accepts zero or more state schema classes and returns a
`frozenset[str]` of all field names annotated with `PrivateStateAttr`.

**Algorithm:**

1. For each schema, get its type hints with `include_extras=True`
   (which preserves `Annotated` metadata).
2. For each field name and annotation, check if the annotation
   contains a `PrivateStateAttr` marker (via the `_has_marker`
   helper).
3. Collect all matching names.

### _has_marker()

```python
def _has_marker(annotation: object, marker: object) -> bool:
```

Recursively checks whether a type annotation contains a specific
marker:

- If the annotation is `Annotated[T, ...]`, check if any metadata
  argument `is` the marker (identity check, not equality).
- If the annotation has a generic origin (e.g., `list[X]`), check
  each argument recursively.
- Otherwise, return `False`.

### Integration with create_deep_agent()

In `create_deep_agent()`, after the middleware stack is assembled:

```python
private_state_keys = private_state_field_names(
    *(mw.state_schema for mw in deepagent_middleware
      if getattr(mw, "state_schema", None) is not None)
)
if sub_agent_middleware is not None:
    sub_agent_middleware.private_state_keys = private_state_keys
```

The private state keys are collected from all middleware that has a
`state_schema` attribute, and forwarded to `SubAgentMiddleware` so
that subagents do not receive private state fields when they are
invoked via the `task` tool.

---

## State Flow Through the Graph

The agent state flows through the graph in a cyclical pattern:

```
Input State
    |
    v
LLM Node (model call)
    |
    v
AI Message (with optional tool calls)
    |
    v
[If tool calls exist]
    |
    v
Tool Node (execute tool calls)
    |
    v
Tool Messages (results)
    |
    v
[Loop back to LLM Node]
    |
[If no tool calls]
    |
    v
Output State
```

### State Mutations at Each Step

1. **LLM Node**: The model receives the current messages and
   produces an `AIMessage`. This message is appended to the
   `messages` channel via the `DeltaChannel` reducer.

2. **Tool Node**: Each tool call is executed. The tool produces a
   `ToolMessage` that is appended to the `messages` channel.
   Tools may also mutate other channels (e.g., `files` via
   `StateBackend`).

3. **Middleware Hooks**: Middleware can mutate state at various
   points:
   - `pre_model`: Before the LLM call (e.g., adding system prompt
     content, summarizing messages).
   - `post_model`: After the LLM call (e.g., patching tool calls).
   - `pre_tool`: Before tool execution (e.g., permission checks).
   - `post_tool`: After tool execution (e.g., updating tool
     results).

### Channels in the State

The agent state typically contains these channels:

| Channel | Type | Reducer | Description |
|---------|------|---------|-------------|
| `messages` | `list[AnyMessage]` | `DeltaChannel(_messages_delta_reducer)` | Conversation history |
| `files` | `dict[str, FileData]` | dict-merge | File storage (when using StateBackend) |
| `remaining_steps` | `int` | (LangGraph internal) | Countdown for recursion limit |
| *middleware fields* | various | various | Additional state from middleware state_schemas |

---

## State Components Summary

| Component | Location | Scope | Persistence |
|-----------|----------|-------|-------------|
| Messages | `state["messages"]` | Per-thread | Checkpointed |
| Files | `state["files"]` | Per-thread | Checkpointed |
| Memory | System prompt (via MemoryMiddleware) | Per-run | Loaded from backend |
| Configuration | `RunnableConfig` | Per-run | Not persisted |
| Private state | Middleware state schemas | Per-step | Checkpointed but not leaked to subagents |
| Todo list | Managed by TodoListMiddleware | Per-thread | Checkpointed |

---

## Checkpointing and DeltaChannel Interaction

Understanding how checkpointing interacts with `DeltaChannel` is
essential for understanding state persistence behavior.

### Without DeltaChannel (Standard Channel)

```
Step 1: checkpoint stores [m1]
Step 2: checkpoint stores [m1, m2]
Step 3: checkpoint stores [m1, m2, m3]
...
Step N: checkpoint stores [m1, m2, ..., mN]

Total storage: 1 + 2 + 3 + ... + N = O(N^2)
```

### With DeltaChannel (snapshot_frequency=50)

```
Step 1:  checkpoint stores delta [m1]
Step 2:  checkpoint stores delta [m2]
...
Step 49: checkpoint stores delta [m49]
Step 50: checkpoint stores SNAPSHOT [m1, m2, ..., m50]
Step 51: checkpoint stores delta [m51]
...
Step 99: checkpoint stores delta [m99]
Step 100: checkpoint stores SNAPSHOT [m1, ..., m100]

Total storage: O(N) -- each message stored in at most one delta
                        plus at most one snapshot
```

### Replay from Checkpoint

To reconstruct the messages list at step 75:

1. Load the snapshot from step 50: `[m1, m2, ..., m50]`
2. Apply deltas for steps 51 through 75
3. The reducer combines the snapshot with each delta batch

Maximum replay cost: `snapshot_frequency - 1` reducer applications
(49 in this case).

### RemoveMessage and Checkpoints

When a `RemoveMessage` tombstone is processed:

1. The message at the indexed position is set to `None` and filtered.
2. The delta stored in the checkpoint is the `RemoveMessage` itself.
3. On replay, the `RemoveMessage` is re-applied to the accumulated
   state, producing the same result.

### REMOVE_ALL_MESSAGES and Checkpoints

When a `REMOVE_ALL_MESSAGES` sentinel is processed:

1. All accumulated state is cleared.
2. Only writes after the sentinel survive.
3. The checkpoint stores the sentinel in the delta.
4. On replay, the sentinel triggers the same full reset.

This mechanism is critical for long-running agents that need to
periodically clear their conversation history (e.g., summarization
middleware that replaces the full history with a summary).
