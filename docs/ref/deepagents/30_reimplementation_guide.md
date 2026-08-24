# 30. Reimplementation Guide

This document targets engineers who need to reimplement the Deep Agents
framework in another language or as a clean-room rebuild. It enumerates the
invariants that must hold, the contracts that pluggable components must satisfy,
the algorithms whose behavior is load-bearing, and the failure modes that a
naive port will encounter.

Throughout this guide, "the reference implementation" refers to the Python
`deepagents` package rooted at `libs/deepagents/deepagents/`.

---

## 30.1 Core Invariants

These invariants are non-negotiable. Violating any of them produces incorrect
behavior that is difficult to diagnose because the symptoms often appear far
from the root cause.

### 30.1.1 Graph Topology

The compiled agent is a LangGraph `CompiledStateGraph` with a ReAct-style
loop:

```
[__start__] --> [agent] --> [tools] --> [agent] --> [__end__]
```

The `agent` node calls the LLM. If the LLM response contains tool calls, the
graph transitions to the `tools` node, which executes them, then loops back to
`agent`. If no tool calls are present, the graph transitions to `__end__`.

**Invariant**: The loop must be unbounded (or bounded by a very large limit).
The reference implementation sets `recursion_limit=9_999`. Do not set a low
limit -- complex coding tasks routinely exceed 100 iterations.

**Invariant**: The `tools` node must execute tool calls in the order they
appear in the LLM response. Tool results must be appended as `ToolMessage`
objects with `tool_call_id` matching the originating `AIMessage`'s
`tool_calls[i].id`.

### 30.1.2 Message Reducer Semantics

The `messages` field uses a custom reducer (`_messages_delta_reducer`) backed
by `DeltaChannel` with `snapshot_frequency=50`. The reducer defines how
concurrent or sequential writes to the messages list are merged.

**Invariant -- Deduplication by ID**: When a new message has the same ID as
an existing message, the new message replaces the existing one in place (same
index position). This is how tool-call patching and message updates work.

**Invariant -- Tombstoning via RemoveMessage**: A `RemoveMessage` with a
matching ID sets the corresponding slot to `None`. The final output filters
out `None` entries. The removal must happen at the correct index (the one
recorded in the ID-to-index map), not by scanning.

**Invariant -- REMOVE_ALL_MESSAGES resets state**: When the sentinel
`REMOVE_ALL_MESSAGES` appears as a `RemoveMessage.id`, the reducer discards
all existing state and all writes that preceded the sentinel in the current
batch. Only writes after the sentinel survive.

**Invariant -- None-ID messages always append**: Messages with `id=None` are
never deduplicated. They are appended unconditionally.

**Invariant -- Coercion on ingest**: Raw dicts, strings, and tuples are
coerced to typed `BaseMessage` objects via `convert_to_messages()` before
dedup logic runs. The reducer must accept heterogeneous input.

**Invariant -- Writes are flattened**: Each write may be a list or a single
message-like. The reducer flattens all writes into a single sequence before
processing.

### 30.1.3 DeltaChannel Checkpoint Storage

`DeltaChannel` provides O(N) total checkpoint storage instead of O(N^2) by
storing only the delta (new writes) between checkpoints, with full snapshots
taken every `snapshot_frequency` checkpoints. The reference implementation
uses `snapshot_frequency=50`.

**Invariant**: Replay must apply deltas in order starting from the most
recent snapshot. A reimplementation that snapshots every checkpoint will be
correct but will use O(N^2) storage for long conversations.

**Invariant**: The reducer must be deterministic. Given the same snapshot and
the same sequence of deltas, replay must produce the identical state. This
rules out random ID assignment inside the reducer (IDs are pre-assigned by
LangGraph's `ensure_message_ids` before the reducer sees them).

### 30.1.4 State Schema Merging

The compiled graph's state schema is the union of:

1. `DeepAgentState` (or a user-provided `state_schema`)
2. Every middleware's `state_schema` (if declared via the `state_schema`
   class attribute)

Fields annotated with `PrivateStateAttr` are omitted from both input and
output schemas. They exist only in the internal state and are invisible to
subagents.

**Invariant**: `PrivateStateAttr` fields must never leak to subagent state.
When `SubAgentMiddleware` dispatches a task, it must strip all
`private_state_keys` from the state passed to the child graph.

**Invariant**: State schema merging must detect conflicting field names with
incompatible types. Two middleware declaring the same field name with
different types is an error.

### 30.1.5 Prompt Assembly Order

The system prompt is assembled from three slots joined by `\n\n`:

```
USER  +  (BASE or CUSTOM)  +  SUFFIX
```

1. `USER`: the `system_prompt=` argument to `create_deep_agent()`.
2. `BASE` or `CUSTOM`: `BASE_AGENT_PROMPT` unless
   `HarnessProfile.base_system_prompt` provides a replacement.
3. `SUFFIX`: `HarnessProfile.system_prompt_suffix` (if set).

**Invariant**: `USER` always leads. Caller instructions must take precedence
over framework defaults.

**Invariant**: `SUFFIX` always trails. Model-tuning guidance sits closest to
the conversation history.

**Invariant**: If `system_prompt` is a structured `SystemMessage` (with
content blocks), the base prompt is appended as an additional text block
rather than string-concatenated. This preserves any image or cache-control
blocks in the user's system message.

### 30.1.6 Recursion Limit

The reference implementation sets `recursion_limit=9_999` on the compiled
graph. This is not a safety measure -- it exists solely to prevent LangGraph
from raising a premature `GraphRecursionError` on long coding sessions.

**Invariant**: Do not lower the recursion limit. Complex tasks (multi-file
refactors, iterative debugging) routinely consume hundreds of agent loop
iterations.

---

## 30.2 Middleware Contract

### 30.2.1 The AgentMiddleware Base Class

```
AgentMiddleware[StateT, ContextT, ResponseT]
```

A middleware is a generic class parameterized over the state type, context
type, and structured response type. It may implement any combination of the
following hooks:

| Hook | Signature | When |
|------|-----------|------|
| `before_agent` | `(state, runtime) -> Command or None` | Once, before the agent loop starts |
| `wrap_model_call` | `(request, handler) -> ModelCallResult` | Around every LLM invocation |
| `after_agent` | `(state, runtime) -> Command or None` | Once, after the agent loop ends |
| `wrap_tool_call` | `(tool, args, config) -> ToolMessage` | Around each tool execution |

All hooks are optional. A middleware that implements none of them is a no-op
(but still occupies its position in the stack).

### 30.2.2 Stack Ordering

The middleware stack is an ordered list. Position matters. The reference
implementation builds the stack in this order:

```
Position  Middleware                        Condition
--------  -------------------------------- ---------
1         TodoListMiddleware               Always
2         SkillsMiddleware                 If skills= provided
3         FilesystemMiddleware             Always (REQUIRED)
4         SubAgentMiddleware               If inline subagents exist (REQUIRED)
5         SummarizationMiddleware          Always
6         PatchToolCallsMiddleware         Always
7         AsyncSubAgentMiddleware          If async subagents provided
---       [user-supplied middleware]        From middleware= parameter
---       [profile extra_middleware]        From HarnessProfile
N+1       _ToolExclusionMiddleware         If profile has excluded_tools
N+2       AnthropicPromptCachingMiddleware Always (no-ops for non-Anthropic)
N+3       MemoryMiddleware                 If memory= provided
N+4       HumanInTheLoopMiddleware         If permissions require it
```

**Invariant -- before_agent hooks run in stack order**: `[0].before_agent`,
then `[1].before_agent`, and so on.

**Invariant -- after_agent hooks run in stack order**: Same left-to-right
order as `before_agent`. This is _not_ reversed.

**Invariant -- wrap_model_call forms an onion**: Middleware `[0]` wraps
`[1]`, which wraps `[2]`, and so on. The innermost handler calls the actual
model. This means `[0]` sees the request first (can pre-process) and sees
the response last (can post-process). Given a stack `[A, B, C]`:

```
A.wrap_model_call(request, handler_for_A)
  -> handler_for_A calls B.wrap_model_call(request, handler_for_B)
       -> handler_for_B calls C.wrap_model_call(request, handler_for_C)
            -> handler_for_C calls the actual model
```

### 30.2.3 ModelRequest Immutability

`ModelRequest` is a frozen dataclass. Middleware must not mutate it directly.
Instead, use `request.override(**kwargs)` to produce a new `ModelRequest`
with selected fields replaced. Direct attribute assignment emits a
`DeprecationWarning` and will become an error.

```
ModelRequest fields:
  model:             BaseChatModel
  messages:          list[AnyMessage]    # excludes system message
  system_message:    SystemMessage | None
  tool_choice:       Any | None
  tools:             list[BaseTool | dict]
  response_format:   ResponseFormat | None
  state:             AgentState
  runtime:           Runtime[ContextT]
  model_settings:    dict[str, Any]
```

The `system_prompt` property is a convenience accessor returning
`system_message.text` or `None`. Setting `system_prompt=` in `override()`
auto-wraps the string in a `SystemMessage`. Specifying both
`system_prompt` and `system_message` simultaneously raises `ValueError`.

### 30.2.4 ModelCallResult Return Types

`wrap_model_call` may return any of three types:

1. **`ModelResponse`**: Contains `result: list[BaseMessage]` and optional
   `structured_response`.
2. **`AIMessage`**: Shorthand -- the framework wraps it in a `ModelResponse`.
3. **`ExtendedModelResponse`**: Contains a `ModelResponse` plus a `Command`
   for additional state updates. Commands go through the graph's reducers.

**Invariant**: When returning an `ExtendedModelResponse`, messages in the
`Command` are added alongside (not replacing) the model response messages.
For non-reducer state fields, the outermost middleware's command wins.

### 30.2.5 Required Middleware Protection

`FilesystemMiddleware` and `SubAgentMiddleware` (when subagents are
configured) are declared as required. They cannot be excluded via
`HarnessProfile.excluded_middleware`. Attempting to exclude them raises
`ValueError` at construction time.

**Invariant**: A reimplementation must refuse to remove required middleware.
These back core agent capabilities (file tools, subagent dispatch) without
which the agent cannot function.

### 30.2.6 Three-Phase Excluded Middleware Pipeline

After the full stack is assembled, `_apply_excluded_middleware()` runs a
three-phase pipeline:

1. **Validate**: Check that no required middleware is targeted for exclusion.
   Raise `ValueError` if so.
2. **Apply**: Remove entries matching exclusion specifications from the stack.
   Entries can be classes (matched by exact type -- not `isinstance()`) or
   strings (matched against `type(mw).__name__`).
3. **Verify**: `_verify_excluded_middleware_coverage()` raises `ValueError` if
   any exclusion entry matched nothing across both the main stack and the
   general-purpose subagent stack. This catches typos and stale profile
   entries.

**Invariant -- Exact type matching**: Exclusion by class uses `type(mw) is
ExcludedClass`, not `isinstance()`. A subclass of an excluded class is NOT
excluded. This prevents accidental removal of middleware that shares an
ancestor.

### 30.2.7 State Schema Contribution

Each middleware may declare a `state_schema` class attribute. This must be a
`TypedDict` subclass of `AgentState`. The framework merges all declared
schemas into the graph's compiled state schema.

```python
class SummarizationState(AgentState):
    _summarization_event: Annotated[SummarizationEvent | None, PrivateStateAttr]

class _DeepAgentsSummarizationMiddleware(AgentMiddleware[SummarizationState, Any, Any]):
    state_schema = SummarizationState
```

The `PrivateStateAttr` annotation hides the field from input and output
schemas. Middleware uses private state to track cross-turn bookkeeping
(iteration counts, summarization events, etc.) without polluting the public
API.

---

## 30.3 Backend Contract

### 30.3.1 BackendProtocol (Abstract Base)

The `BackendProtocol` ABC defines the file operation interface. All
operations accept and return paths starting with `/`.

| Method | Return type | Purpose |
|--------|-------------|---------|
| `ls` | `LsResult` | List directory contents with metadata |
| `read` | `ReadResult` | Read file content with line numbers (cat -n format) |
| `write` | `WriteResult` | Write or create a file |
| `edit` | `EditResult` | Apply a string replacement in a file |
| `grep` | `GrepResult` | Search file contents by literal substring |
| `glob` | `GlobResult` | Find files by glob pattern |
| `upload_files` | `FileUploadResponse` | Upload multiple files |
| `download_files` | `FileDownloadResponse` | Download file content |

Each method has a sync variant and an `a`-prefixed async variant (e.g.,
`als`, `aread`). The default async implementation delegates to
`asyncio.to_thread(self.sync_method, ...)`.

**Invariant -- `read` returns cat -n format**: Output is formatted with line
numbers starting at 1. Lines longer than 2000 characters are truncated. This
format is load-bearing because the LLM uses line numbers for navigation and
the `edit` tool references them in error messages.

**Invariant -- `grep` is literal substring matching**: Not regex. The `grep`
tool performs exact substring matching within file content. The `glob`
parameter on `grep` filters which files to search, not what content to
match.

**Invariant -- `edit` is exact string replacement**: The `old_string` must
appear exactly once in the file. If it appears zero times, the edit fails
(content not found). If it appears more than once, the edit is ambiguous and
must fail. This constraint prevents the LLM from making unintended bulk
replacements.

### 30.3.2 SandboxBackendProtocol

Extends `BackendProtocol` with shell execution:

| Method | Return type | Purpose |
|--------|-------------|---------|
| `execute` | `ExecuteResponse` | Run a shell command (sync) |
| `aexecute` | `ExecuteResponse` | Run a shell command (async) |

`ExecuteResponse` contains `output: str`, `exit_code: int`, and timeout
status. The default execute timeout is 120 seconds.

### 30.3.3 Concrete Backend Implementations

| Backend | Shell? | Storage | Use case |
|---------|--------|---------|----------|
| `StateBackend` | No | In LangGraph agent state (ephemeral) | Testing, stateless |
| `FilesystemBackend` | No | Local filesystem (disk I/O) | Read/write to disk |
| `LocalShellBackend` | Yes | Local filesystem + subprocess | CLI/development |
| `StoreBackend` | No | Persistent via LangGraph BaseStore | Cloud deployments |
| `BaseSandbox` | Yes | Remote sandbox (Docker, VMs) | Production isolation |

### 30.3.4 StateBackend Read-Your-Writes

`StateBackend` stores files in the LangGraph agent state (the `files` field
of `DeepAgentState`). Because LangGraph state updates are batched at node
boundaries, a naive implementation creates a stale-read problem: a file
written in one tool call is invisible to a subsequent tool call within the
same `tools` node execution.

**Invariant -- Read-your-writes**: `StateBackend` must read from fresh state
using `CONFIG_KEY_READ` with `fresh=True`. This bypasses the batched state
and reads the most recent channel values.

**Invariant -- Atomic writes via CONFIG_KEY_SEND**: Writes use
`CONFIG_KEY_SEND` to push updates into the state channel immediately,
ensuring subsequent reads within the same node see the updated value.

A reimplementation that uses a different state management system must solve
the same problem: multiple tool calls within one graph step must see each
other's writes.

### 30.3.5 CompositeBackend Routing

`CompositeBackend` routes operations to different backends based on path
prefixes:

1. **Longest prefix wins**: `/memories/notes/` matches before `/memories/`.
2. **Fan-out for path-less operations**: `grep` with no path filter fans out
   to all backends and merges results.
3. **Path remapping**: Results from sub-backends have their paths remapped
   so they appear to come from a unified namespace.

```
composite = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend()}
)

composite.write("/temp.txt", "ephemeral")      # -> StateBackend
composite.write("/memories/note.md", "stored")  # -> StoreBackend
```

### 30.3.6 FileData Structure

All file data is represented as dicts:

```
{
    "content": str,       # Text content (utf-8) or base64-encoded binary
    "encoding": str,      # "utf-8" for text, "base64" for binary data
    "created_at": str,    # ISO format timestamp
    "modified_at": str,   # ISO format timestamp
}
```

**Invariant -- Legacy format support**: Legacy data may contain
`"content": list[str]` (lines split on `\n`). Backends must accept this
for backwards compatibility and emit a deprecation warning. New writes must
use the string format (FileFormat v2).

---

## 30.4 Key Algorithms to Replicate

These algorithms have subtle correctness properties. A reimplementation must
match their behavior, not just their interface.

### 30.4.1 Messages Reducer

The full algorithm in pseudocode:

```
function messages_delta_reducer(state, writes):
    # Phase 1: Flatten writes
    flat = []
    for w in writes:
        if w is a list:
            flat.extend(w)
        else:
            flat.append(w)

    # Phase 2: Coerce to typed messages
    state_msgs = convert_to_messages(state or [])
    msgs = convert_to_messages(flat)

    # Phase 3: Handle REMOVE_ALL_MESSAGES sentinel
    remove_all_idx = None
    for idx, m in enumerate(msgs):
        if m is RemoveMessage and m.id == REMOVE_ALL_MESSAGES:
            remove_all_idx = idx
    if remove_all_idx is not None:
        state_msgs = []
        msgs = msgs[remove_all_idx + 1 :]

    # Phase 4: Build result with ID-based index
    result = []     # list of (message | None)
    index = {}      # id -> position in result

    for m in state_msgs:
        if m.id is not None:
            index[m.id] = len(result)
        result.append(m)

    for msg in msgs:
        if msg.id is None:
            result.append(msg)              # Always append
        elif msg is RemoveMessage:
            if msg.id in index:
                result[index[msg.id]] = None    # Tombstone
                delete index[msg.id]
        elif msg.id in index:
            result[index[msg.id]] = msg     # Replace in-place
        else:
            index[msg.id] = len(result)
            result.append(msg)              # New message

    # Phase 5: Compact
    return [m for m in result if m is not None]
```

**Critical detail**: Replacement happens at the original index position, not
at the end. This preserves message ordering, which matters for context
window management and summarization.

**Critical detail**: The `REMOVE_ALL_MESSAGES` scan finds the _last_
occurrence of the sentinel, not the first. All writes before that last
sentinel are discarded.

**Critical detail**: `state` may be `None` (for `DeltaChannel.replay_writes`
on threads whose earliest checkpoint did not seed `messages: []`). The
algorithm must treat `None` as the empty list.

### 30.4.2 Nonce-Bracketed XML for Rubric Grading

The rubric grading system wraps payloads in nonce-delimited XML to defend
against prompt injection from agent output:

```
nonce = random_hex(8)    # secrets.token_hex(8)

rubric_xml = f"<rubric-{nonce}>{sanitize(rubric_text)}</rubric-{nonce}>"
transcript_xml = f"<transcript-{nonce}>{sanitize(transcript)}</transcript-{nonce}>"
```

The sanitization function escapes closing tags:

```
PAYLOAD_CLOSER_RE = regex(r"</(rubric|transcript)", IGNORECASE)

function sanitize(content):
    return PAYLOAD_CLOSER_RE.sub(r"<\/\1", content)
```

This prevents premature tag closure that could let adversarial content
escape the bracketed region and inject instructions to the grader.

**Invariant**: The nonce must be cryptographically random and generated fresh
for each grading invocation. Reusing nonces allows pre-computed injection
attacks.

**Invariant**: The sanitization regex must be case-insensitive. Mixed-case
closing tags (`</Rubric>`, `</TRANSCRIPT>`) are a viable injection vector.

**Invariant**: The grader response is validated via a structured output
model (`GraderResponse`) with a model validator that checks consistency
between the `result` field and `criteria` satisfaction flags. A grader
claiming "satisfied" while individual criteria are marked unsatisfied is
rejected.

### 30.4.3 Summarization Trigger Logic

The summarization middleware monitors token usage and triggers context
compression when thresholds are exceeded.

**Trigger mechanism**: `TriggerClause` objects define conditions. Within a
single clause, all conditions must be true (AND semantics). Across clauses,
any satisfied clause triggers summarization (OR semantics).

**Default trigger**: The default configuration fires at approximately 85% of
the model's context window, or at a fixed threshold of 170,000 tokens
(whichever is lower).

**Pre-summarization clipping**: `TruncateArgsSettings` controls argument
clipping before the summarizer runs. Large `write_file` and `edit_file`
arguments from old tool calls are truncated to prevent the summarizer
itself from exceeding the context window.

**History offload**: Before removing old messages, the full text is written
to a file in the backend for audit purposes.

**Fallback**: If the LLM returns a `ContextOverflowError`, summarization is
triggered as an emergency measure.

**Invariant**: Token counting must use the same tokenizer the model uses.
Mismatched tokenizers cause premature or late triggering, both of which
degrade quality.

### 30.4.4 Tool Exclusion

`_ToolExclusionMiddleware` filters tools before each LLM call:

```
function wrap_model_call(request, handler):
    filtered = [t for t in request.tools if tool_name(t) not in excluded]
    return handler(request.override(tools=filtered))
```

The `tool_name()` helper extracts the name from either a `BaseTool` object
(via `.name` attribute) or a dict-format tool (via
`["function"]["name"]`).

**Invariant**: Exclusion operates on the tool _name_ string, not the tool
class. Two tools with the same name are both excluded.

**Invariant**: Tool exclusion happens at the middleware level (modifying what
the LLM sees), not at the tool execution level. The LLM never sees excluded
tools and therefore never attempts to call them.

### 30.4.5 Overflow Clipping

When a `ContextOverflowError` occurs, `_clip_overflow_tail` acts as a
last-resort safety valve:

- **`read_file` results**: Head-sliced to approximately 4,000 characters
  with a pointer notice directing the model to the full file path.
- **Other tool results**: Fully offloaded to
  `/large_tool_results/{tool_call_id}` in the backend, replaced with a
  pointer message.

**Invariant**: The pointer message must include enough information for the
model to retrieve the full result (file path and tool call ID). Without
this, the model loses access to the tool output permanently.

### 30.4.6 Profile Merge Semantics

When multiple `HarnessProfile` matches exist, they are merged with these
rules:

| Field type | Merge strategy |
|-----------|---------------|
| Scalar (`base_system_prompt`, `system_prompt_suffix`) | More-specific wins (later in resolution order) |
| `frozenset` (`excluded_tools`, `excluded_middleware`) | Set union |
| Middleware lists (`extra_middleware`) | Type-keyed merge: same class replaces, novel class appends |
| `GeneralPurposeSubagentProfile` | Field-wise merge: non-`None` wins per field |

Resolution order (from most specific to least):

1. `"provider:model"` (exact spec)
2. `"model"` (identifier only, if the original spec contained a colon)
3. `"provider"` (provider prefix)
4. `""` (global defaults)

**Invariant**: More-specific profiles override less-specific ones for
scalars. For sets, all exclusions accumulate (union). For middleware
lists, same-type middleware from a more-specific profile replaces the
less-specific instance rather than duplicating it.

### 30.4.7 Subagent State Processing

When `SubAgentMiddleware` dispatches a task to a child agent:

1. **Strip private state**: All keys listed in `private_state_keys` are
   removed from the state dict passed to the child. This prevents internal
   bookkeeping (summarization events, todo items, middleware counters)
   from leaking to subagents.
2. **Share file state**: The `files` channel is passed through so subagents
   can read files the parent has accessed.
3. **Fresh message history**: The subagent starts with a single
   `HumanMessage` containing the task description.
4. **Merge results back**: The subagent's state changes (file writes) are
   merged back into the parent state via `Command(update=...)`.
5. **Response extraction**: The last non-empty `AIMessage.content` (or
   `structured_response` if configured) is returned as the tool result.

---

## 30.5 Extension Points

These are the intended interfaces for extending the framework without
modifying core code.

### 30.5.1 Custom Middleware

Create a subclass of `AgentMiddleware` and pass it via the `middleware=`
parameter to `create_deep_agent()`. User middleware is inserted after the
built-in middleware (after `PatchToolCallsMiddleware` and any
`AsyncSubAgentMiddleware`) but before `_ToolExclusionMiddleware`,
`AnthropicPromptCachingMiddleware`, `MemoryMiddleware`, and
`HumanInTheLoopMiddleware`.

```python
class MyMiddleware(AgentMiddleware[MyState, Any, Any]):
    state_schema = MyState  # Optional: adds fields to the state schema

    def wrap_model_call(self, request, handler):
        modified = request.override(
            system_message=SystemMessage(content="Extra instructions"),
        )
        response = handler(modified)
        # Post-process response here
        return response
```

Decorator-style hooks are also available for simpler cases:

| Decorator | Equivalent hook |
|-----------|-----------------|
| `@before_agent` | `before_agent()` |
| `@after_agent` | `after_agent()` |
| `@wrap_model_call` | `wrap_model_call()` |
| `@wrap_tool_call` | `wrap_tool_call()` |

### 30.5.2 Custom Backends

Subclass `BackendProtocol` or `SandboxBackendProtocol`. The most common
pattern for production use is subclassing `BaseSandbox`, which derives all
file operations from `execute()`:

- Override `execute()` and `aexecute()` to run commands in your sandbox
  environment.
- Override `upload_files()` to transfer files into the sandbox.
- All other file operations (`read`, `write`, `edit`, `grep`, `glob`, `ls`)
  are automatically implemented via shell commands routed through
  `execute()`, ensuring they run within the sandbox boundary.

Base64 encoding (`MAX_BINARY_BYTES = 500 * 1024`) is used for parameter
passing to avoid shell injection.

### 30.5.3 Custom Profiles

Register profiles via either API calls or entry points:

**API registration**:
```python
register_provider_profile("my_provider", ProviderProfile(...))
register_harness_profile("my_provider:my_model", HarnessProfile(...))
```

**Entry point registration** (for third-party plugins):
- `deepagents.provider_profiles` -- calls `register_provider_profile()`
- `deepagents.harness_profiles` -- calls `register_harness_profile()`

Built-in profiles load first. Third-party plugins layer on top via additive
merge. Bootstrap is lazy (on first registry access) and thread-safe.

### 30.5.4 BackendFactory (removed)

> **Changed:** the current SDK has **no** `BackendFactory` type. The `backend`
> argument is a `BackendProtocol` instance or `None`. If you need
> runtime-dependent behavior (e.g. a thread-scoped store namespace), use the
> backend's own mechanisms — for example `StoreBackend` takes a
> `NamespaceFactory` (`Callable[[Runtime], tuple[str, ...]]`). When rebuilding,
> do not reproduce a lazy backend-factory parameter; pass a constructed backend.

### 30.5.5 Subagent Configuration

Subagents are configured as dictionaries with these keys:

- `agent_name`: Identifier shown to the parent agent.
- `description`: Description the parent model sees to decide when to
  delegate.
- `model`: Model string or `BaseChatModel` instance.
- `system_prompt`: Subagent-specific system prompt.
- `tools`: Tool list for the subagent.
- `permissions`: Optional `FilesystemPermission` list (replaces parent
  permissions entirely -- no merge).

A general-purpose subagent is auto-added as the first entry in the inline
subagents list when `_profile.general_purpose_subagent` is configured. This
subagent inherits the parent's backend, merged permissions, and a
profile-aware system prompt.

For advanced use cases, `CompiledSubAgent` accepts a pre-built
`CompiledStateGraph`, serving as an escape hatch for subagents that do not
fit the standard agent loop (retrieval pipelines, multi-step verification
workflows, custom graph topologies).

### 30.5.6 Filesystem Permissions

`FilesystemPermission` provides a rule-based access control system:

```
FilesystemPermission:
    operations: list[FilesystemOperation]  # ["read"], ["write"], or both
    paths: list[str]                        # glob patterns
    mode: "allow" | "deny" | "interrupt"
```

Rules are evaluated in declaration order; first matching rule wins. If no
rule matches, the operation is allowed (open by default). When any
permission uses `mode="interrupt"`, `HumanInTheLoopMiddleware` is
automatically installed.

**Invariant**: Permissions are enforced at the tool level by
`FilesystemMiddleware`, not at the backend level. Direct backend calls
bypass permissions entirely. This is intentional -- internal framework code
(memory writes, overflow clipping) needs unrestricted backend access.

---

## 30.6 Common Pitfalls

### 30.6.1 Snapshot-Every-Checkpoint

Storing a full state snapshot at every checkpoint causes O(N^2) total
storage for N checkpoints. The `DeltaChannel` mechanism with
`snapshot_frequency=50` reduces this to O(N). A reimplementation that
checkpoints naively will run out of memory or storage on long conversations
(thousands of messages). The fix is to store only deltas between snapshots
and take full snapshots at regular intervals.

### 30.6.2 Stale Reads in StateBackend

LangGraph batches state updates at node boundaries. If tool A writes a file
and tool B reads it within the same `tools` node, tool B sees the pre-write
state unless `CONFIG_KEY_READ` with `fresh=True` is used. The reference
implementation solves this with read-your-writes semantics via
`CONFIG_KEY_READ` and `CONFIG_KEY_SEND`. A reimplementation must provide
equivalent immediate visibility of writes within the same node execution.

### 30.6.3 Message ID Assignment in the Reducer

Do not assign message IDs inside the reducer. LangGraph's
`ensure_message_ids` stamps stable UUIDs onto all `BaseMessage` writes
before they are serialized to the checkpoint. By the time the reducer runs,
every message already has a stable ID. Assigning IDs in the reducer is
redundant and fragile -- on replay, a randomly-assigned ID would differ
from the stored checkpoint, causing deserialization mismatches.

### 30.6.4 isinstance() for Middleware Exclusion

Using `isinstance()` instead of exact type matching (`type(mw) is
ExcludedClass`) for middleware exclusion will accidentally remove middleware
subclasses that share an ancestor. The reference implementation uses exact
type matching deliberately. A `SubclassOfFoo` should not be excluded when
`Foo` is in the exclusion list.

### 30.6.5 Reversed after_agent Order

It is tempting to run `after_agent` hooks in reverse stack order (like
destructors in C++). The reference implementation does NOT do this -- both
`before_agent` and `after_agent` run in forward stack order. Reversing
`after_agent` will break middleware that depends on its position relative to
other middleware in the cleanup phase.

### 30.6.6 Missing Sanitization in Rubric Grading

Omitting the `_sanitize_for_payload` step in rubric grading creates a
prompt injection vulnerability. Without sanitizing closing tags in the
payload, adversarial agent output can include `</rubric>` or
`</transcript>` to escape the nonce-bracketed region and inject arbitrary
instructions to the grader.

### 30.6.7 System Prompt Concatenation Order

Reversing the prompt assembly order (putting `BASE` before `USER`) causes
caller instructions to be overridden by framework defaults. The caller's
system prompt must always lead so that explicit instructions take precedence.
Placing the suffix in any position other than trailing causes model-tuning
guidance to be separated from the conversation history, reducing its
effectiveness.

### 30.6.8 Tool Exclusion at Execution vs. Visibility

Excluding a tool at execution time (refusing to run it when called) rather
than at visibility time (not showing it to the LLM) causes the model to
repeatedly attempt to use the excluded tool, wasting tokens and iterations.
The reference implementation removes excluded tools from the `tools` list
in the `ModelRequest`, so the LLM never sees them. A reimplementation must
do the same.

### 30.6.9 Permission Enforcement at the Backend Layer

Enforcing filesystem permissions at the backend layer (inside `read()`,
`write()`, etc.) instead of at the middleware layer breaks the architecture
in two ways:

1. Internal framework code that needs unrestricted backend access (e.g.,
   memory writes, overflow clipping) is blocked by permissions.
2. The `interrupt` mode cannot function because the backend has no access
   to the human-in-the-loop mechanism.

Permissions must be enforced at the tool/middleware level.

### 30.6.10 Insufficient Recursion Limit

Setting a low `recursion_limit` (e.g., 25 or 50) causes
`GraphRecursionError` on complex tasks. The agent loop is designed to run
for hundreds of iterations on multi-file coding tasks. The limit exists
only as a safeguard against infinite loops, not as a performance tuning
parameter.

### 30.6.11 Forgetting REMOVE_ALL_MESSAGES in the Reducer

The `REMOVE_ALL_MESSAGES` sentinel is used by the summarization middleware
to clear the message history before inserting a condensed summary. If the
reducer does not handle this sentinel, summarization silently fails -- the
old messages remain alongside the summary, doubling context usage and
causing confusion.

### 30.6.12 Tool Call / Tool Result Misalignment

LLM APIs require that every tool call has a corresponding `ToolMessage` with
the matching `tool_call_id`. If you lose this alignment (e.g., by removing
messages during summarization without preserving pair boundaries), the API
call fails. Always partition messages at pair boundaries when truncating or
summarizing.

---

## 30.7 Testing Strategy

### 30.7.1 Reducer Round-Trip Tests

The messages reducer is the most critical low-level component. Test at
minimum:

1. **Append**: Fresh state, write N messages, verify all appear in order.
2. **Dedup by ID**: Write a message with ID "x", then write another message
   with the same ID "x". Verify the second replaces the first at the same
   index position.
3. **RemoveMessage**: Write three messages, then send a `RemoveMessage` for
   the middle one. Verify the result has two messages in the correct order.
4. **REMOVE_ALL_MESSAGES**: Write messages, then send the sentinel, then
   write more. Verify only the post-sentinel messages survive.
5. **None-ID append**: Write messages with `id=None`. Verify they are never
   deduplicated, even when identical.
6. **Coercion**: Pass raw dicts and strings. Verify they are coerced to
   typed `BaseMessage` objects.
7. **Batch flattening**: Pass a mix of lists and single messages as writes.
   Verify they are all flattened correctly.
8. **Idempotent replay**: Apply the same delta sequence twice from the same
   snapshot. Verify the result is identical both times.
9. **None state**: Pass `state=None`. Verify it is treated as the empty list
   without raising an exception.

### 30.7.2 Middleware Stack Tests

1. **Ordering**: Construct a stack of three test middleware that each record
   their invocation. Verify `before_agent` fires in order `[0, 1, 2]` and
   `after_agent` fires in the same order `[0, 1, 2]`.
2. **Onion wrapping**: Construct a stack of three middleware that each
   prepend/append markers to the system prompt. Verify the markers appear in
   the correct nested order.
3. **Required protection**: Attempt to exclude `FilesystemMiddleware` via
   profile. Verify `ValueError` is raised.
4. **Exclusion coverage**: Add an exclusion entry that matches nothing.
   Verify `ValueError` is raised by the coverage verification step.
5. **Exact type matching**: Create `class FooSub(FooMiddleware)`. Exclude
   `FooMiddleware`. Verify `FooSub` is NOT excluded.
6. **ModelRequest immutability**: Verify that `override()` returns a new
   object and does not mutate the original.
7. **State schema merging**: Create two middleware with compatible
   `state_schema` declarations. Verify the merged schema contains all
   fields.

### 30.7.3 Backend Contract Tests

For each backend implementation, test:

1. **Write-then-read**: Write a file, read it back, verify content and
   line-number formatting.
2. **Edit**: Write a file, edit with a unique old_string, read back, verify
   the replacement was applied.
3. **Edit ambiguity**: Write a file with a duplicated string, attempt edit,
   verify failure.
4. **Edit not found**: Attempt to edit with a non-existent old_string,
   verify failure.
5. **grep**: Write multiple files, grep for a substring, verify correct
   file matches.
6. **ls**: Create a directory structure, list it, verify entries and
   metadata.
7. **glob**: Create files matching and not matching a pattern, verify
   correct results.

For `StateBackend` specifically:

8. **Read-your-writes**: Within a simulated node execution, write then read.
   Verify the read returns the written content, not the pre-write state.
9. **FileFormat compatibility**: Verify that legacy `list[str]` content and
   modern string content are both handled correctly.
10. **None-state initialization**: Invoke with no `files` key in the input.
    Verify the backend handles the empty state gracefully.

### 30.7.4 CompositeBackend Routing Tests

1. **Longest prefix**: Configure routes `/a/` and `/a/b/`. Write to
   `/a/b/c`. Verify it routes to the `/a/b/` backend, not the `/a/`
   backend.
2. **Default fallback**: Write to a path matching no route. Verify it routes
   to the default backend.
3. **Fan-out grep**: Grep with no path filter. Verify results from all
   backends are merged with correct path remapping.

### 30.7.5 Profile Resolution Tests

1. **Exact match**: Register a profile for `"anthropic:claude-sonnet-4-20250514"`.
   Resolve with that exact spec. Verify the profile is returned.
2. **Provider fallback**: Register a profile for `"anthropic"`. Resolve with
   `"anthropic:some-new-model"`. Verify the provider profile is used.
3. **Merge**: Register profiles at provider and exact-spec levels. Verify
   scalars are overridden by the more-specific profile, sets are unioned,
   and middleware lists are type-merged.
4. **Default profile**: Register a profile for `""`. Verify it applies to
   all models.
5. **Exclusion typo detection**: Register a profile with an exclusion that
   matches no middleware. Verify the verification step raises an error.

### 30.7.6 Prompt Assembly Tests

1. **USER + BASE**: Provide a `system_prompt=` argument. Verify it appears
   before `BASE_AGENT_PROMPT` in the final prompt.
2. **Custom replaces base**: Set `HarnessProfile.base_system_prompt`. Verify
   it replaces `BASE_AGENT_PROMPT`.
3. **Suffix appended**: Set `HarnessProfile.system_prompt_suffix`. Verify it
   appears at the end.
4. **SystemMessage preservation**: Provide a `SystemMessage` with content
   blocks. Verify the base prompt is appended as an additional text block,
   not string-concatenated into existing blocks.

### 30.7.7 Rubric Sanitization Tests

1. **Clean content**: Pass content without closing tags. Verify it passes
   through unchanged.
2. **Closing tag escape**: Pass content containing `</rubric>`. Verify it is
   escaped to `<\/rubric>`.
3. **Case insensitivity**: Pass `</RUBRIC>` and `</Transcript>`. Verify
   both are escaped.
4. **Nonce uniqueness**: Invoke grading twice. Verify the nonces differ.
5. **GraderResponse validation**: Submit a response claiming "satisfied"
   with unsatisfied criteria. Verify the validator rejects it.

### 30.7.8 End-to-End Scenario Tests

Test at least these scenarios against the fully compiled agent:

1. **Simple Q&A**: Invoke with a factual question. Verify the agent
   responds without tool calls.
2. **File read**: Invoke with a request to read a file that exists in the
   backend. Verify the agent calls the `read_file` tool and incorporates
   the result.
3. **File edit**: Invoke with a request to modify a file. Verify the agent
   calls `edit_file` with correct `old_string`/`new_string` and the file
   is updated.
4. **Subagent delegation**: Configure a subagent. Invoke with a task
   matching the subagent's description. Verify the `task` tool is called
   and the subagent's response is incorporated.
5. **Context overflow / summarization**: Feed enough messages to trigger
   summarization. Verify the message list is compressed and the agent
   continues functioning.
6. **Permission denial**: Configure a `deny` permission. Attempt the
   denied operation. Verify the tool returns a permission-denied error.
7. **Permission interrupt**: Configure an `interrupt` permission. Attempt
   the operation. Verify the graph pauses for human approval.

### 30.7.9 Checkpoint and Replay Tests

1. **Resume from checkpoint**: Run an agent for several turns, save the
   checkpoint, create a new agent instance from the checkpoint, verify
   the conversation continues correctly.
2. **Delta replay**: Accumulate 100+ messages across multiple checkpoints.
   Replay from the most recent snapshot using stored deltas. Verify the
   final state matches a full snapshot taken at the same point.
3. **Cross-version compatibility**: Serialize a checkpoint with FileFormat
   v1, load it with a v2 reader. Verify backwards compatibility.

---

## Cross-References

- [06. Graph Construction](06_graph.md) -- Detailed walkthrough of
  `create_deep_agent()` and the compiled graph topology.
- [07. State Management](07_state.md) -- `DeepAgentState`, reducers,
  `PrivateStateAttr`, and checkpointing.
- [11. Middleware Overview](11_middleware_overview.md) -- `AgentMiddleware`
  base class, hooks, and composition.
- [28. Execution Flows](28_execution_flows.md) -- Six traced execution
  scenarios showing the full middleware and state pipeline in action.
- [29. Architecture Reference](29_architecture.md) -- Component
  relationships, security model, and deployment targets.
