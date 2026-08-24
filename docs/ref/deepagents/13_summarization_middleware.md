# Summarization Middleware -- Exhaustive Reference

Source file: `libs/deepagents/deepagents/middleware/summarization.py` (~1790 lines)

---

## 1. Purpose and Motivation

Large language models have a finite context window. As an agent-driven conversation
grows -- accumulating human messages, AI responses, tool calls and tool results --
the total token count eventually approaches or exceeds the model's maximum input
capacity. When that happens, the provider rejects the request with a
`ContextOverflowError` and the agent loop halts.

The summarization middleware exists to prevent that failure mode. It monitors the
token count of the conversation and, when a configurable threshold is reached,
compacts the older portion of the conversation into a short LLM-generated summary.
The original messages are offloaded to a backend (typically a filesystem path like
`/conversation_history/{thread_id}.md`) so the agent can retrieve them later via
`read_file` if it needs the details.

Without this middleware, long-running agents (code assistants, research loops,
multi-step planning tasks) would inevitably crash once the conversation exceeds the
model's input limit.

### Why Deep Agents wraps the LangChain upstream

LangChain provides its own `SummarizationMiddleware` at
`langchain.agents.middleware.summarization`. The Deep Agents version
(`_DeepAgentsSummarizationMiddleware`) wraps it to add several behaviors that
long-running, file-aware agents need:

1. **Backend offload of evicted history.** Evicted messages are appended to
   `/conversation_history/{thread_id}.md` on the configured backend before the
   summary replaces them. The summary message embeds that path so the agent can
   re-open it via `read_file`. LangChain drops evicted messages with no recovery
   path.

2. **Pre-summarization tool-argument truncation.** Large `write_file` / `edit_file`
   arguments in older messages are clipped at a lower threshold than full compaction,
   often reclaiming enough context to skip summarization entirely.

3. **`ContextOverflowError` fallback.** If the provider rejects the request with
   a context-overflow error, the middleware catches it, summarizes, and retries
   instead of bubbling the error up.

4. **Non-mutating message state.** Summarization is tracked in a private
   `_summarization_event` field via `wrap_model_call`, leaving `state["messages"]`
   intact. LangChain rewrites the state with `RemoveMessage(id=REMOVE_ALL_MESSAGES)`
   from `before_model`. Preserving the raw log enables replay, evaluations, and
   shared state with the `compact_conversation` tool.

5. **Auto-selected trigger/keep thresholds.** The `create_summarization_middleware`
   factory picks fraction-based defaults from the model's profile when
   `max_input_tokens` is exposed, falling back to fixed counts otherwise.

---

## 2. Architecture Overview

The system consists of two middleware classes, two factory functions, and several
supporting TypedDicts and helper functions.

### Class hierarchy

```
AgentMiddleware (langchain base)
  |
  +-- _DeepAgentsSummarizationMiddleware   (auto-summarization engine)
  |       Public alias: SummarizationMiddleware
  |
  +-- SummarizationToolMiddleware          (compact_conversation tool provider)
```

### Factory functions

- `create_summarization_middleware(model, backend, ...)` -- Creates a
  `SummarizationMiddleware` with model-aware defaults.
- `create_summarization_tool_middleware(model, backend, ...)` -- Creates both a
  `SummarizationMiddleware` and wraps it in a `SummarizationToolMiddleware`.

### Supporting types

- `SummarizationState` -- TypedDict extending `AgentState` with
  `_summarization_event`.
- `SummarizationEvent` -- TypedDict representing a single summarization event.
- `TriggerClause` -- TypedDict for AND-semantics trigger conditions.
- `TruncateArgsSettings` -- TypedDict for tool-argument truncation configuration.
- `SummarizationDefaults` -- TypedDict for model-profile-derived defaults.
- `CompactConversationSchema` -- Pydantic `BaseModel` for the compact tool schema.

---

## 3. The Two-Middleware Design

The summarization system deliberately separates into two middleware instances that
occupy different positions in the middleware stack and serve complementary roles.

### SummarizationMiddleware (auto-summarization engine)

Position in the default `create_deep_agent` stack: **after SubAgentMiddleware, before
PatchToolCallsMiddleware**. In the base stack ordering documented in `graph.py`:

```
Base stack (no TodoListMiddleware — it is a harness-profile opt-in):
  1. SkillsMiddleware (if skills provided)
  2. FilesystemMiddleware
  3. SubAgentMiddleware (if inline subagents available)
  4. SummarizationMiddleware              <-- HERE
  5. PatchToolCallsMiddleware
  6. AsyncSubAgentMiddleware (if async subagents provided)
```

This middleware intercepts `wrap_model_call` to check whether summarization is needed
before every model invocation. It does not provide any tools.

**Registration** (from `graph.py`, line 779):

```python
deepagent_middleware.extend(
    [
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
    ]
)
```

### SummarizationToolMiddleware (compact tool provider)

This middleware is **not** added by default in `create_deep_agent`. It is provided
as an opt-in for callers who want to give the agent a `compact_conversation` tool
that the model can call proactively, or that a human-in-the-loop flow can trigger.

When used, it is typically passed in the `middleware=` list of `create_deep_agent`,
which places it in the "user middleware" slot between the base stack and the tail
stack.

This middleware:
- Registers a `compact_conversation` tool via its `self.tools` attribute.
- Injects a system-prompt nudge via `wrap_model_call` telling the model about the
  tool.
- Delegates all actual summarization work to the `SummarizationMiddleware` instance
  it wraps.

### How they share state

Both middleware classes declare `state_schema = SummarizationState`, which adds the
private field `_summarization_event` to the agent state. This shared key is how the
auto-summarization engine and the manual compact tool coordinate:

- When `SummarizationMiddleware` performs a summarization, it writes a new
  `SummarizationEvent` to `_summarization_event` via an `ExtendedModelResponse`.
- When `SummarizationToolMiddleware`'s compact tool runs, it reads the existing
  `_summarization_event` to reconstruct effective messages, then writes a new event
  via `Command(update=...)`.
- On the next model call, `SummarizationMiddleware` reads the event (regardless of
  who wrote it) to reconstruct the effective message list.

---

## 4. Token Counting and Threshold Logic

### The trigger system

The `trigger` parameter controls when automatic summarization fires. It accepts
several formats (see `__init__`, line 289):

```python
trigger: ContextSize | TriggerClause | list[ContextSize | TriggerClause] | None
```

Where `ContextSize` is a tuple of `(kind, value)` with `kind` being one of:
- `"tokens"` -- absolute token count
- `"messages"` -- absolute message count
- `"fraction"` -- fraction of the model's `max_input_tokens`

A `TriggerClause` is a dictionary with AND semantics (all conditions must be met):

```python
class TriggerClause(TypedDict, total=False):
    tokens: int
    messages: int
    fraction: float
```

A list of triggers combines items with OR semantics (any one must be met).

### Model-aware defaults

The `compute_summarization_defaults` function (line 223) selects thresholds based on
whether the model exposes a profile with `max_input_tokens`:

**With profile** (has `max_input_tokens`):
```python
{
    "trigger": ("fraction", 0.85),
    "keep": ("fraction", 0.10),
    "truncate_args_settings": {
        "trigger": ("fraction", 0.85),
        "keep": ("fraction", 0.10),
    },
}
```

**Without profile** (fallback):
```python
{
    "trigger": ("tokens", 170000),
    "keep": ("messages", 6),
    "truncate_args_settings": {
        "trigger": ("messages", 20),
        "keep": ("messages", 20),
    },
}
```

### Token counting

The `_count_tokens` method (line 756) handles three cases depending on whether the
configured `token_counter` accepts a `tools` keyword argument:

```python
def _count_tokens(
    self,
    messages: list[AnyMessage],
    system_message: SystemMessage | None,
    tools: list[BaseTool | dict[str, Any]] | None,
) -> int:
```

The token counter is inspected once at construction time via
`_token_counter_accepts_tools` (line 188). If the counter's signature includes
`tools` or `**kwargs`, tools are included in the count. If the signature is
opaque (C-level callables), a runtime probe is used. The default counter is
`count_tokens_approximately` from `langchain_core.messages.utils`.

The system message, if present, is prepended to the message list before counting
(line 779):

```python
counted_messages = [system_message, *messages] if system_message is not None else messages
```

### The decision function

The `_should_summarize` method (line 410) delegates to the LangChain helper:

```python
def _should_summarize(self, messages: list[AnyMessage], total_tokens: int) -> bool:
    return self._lc_helper._should_summarize(messages, total_tokens)
```

This evaluates the configured trigger clauses against the current token count and
message count.

---

## 5. The Summarization Process

When `wrap_model_call` determines that summarization is needed (or when
`ContextOverflowError` forces it), the following sequence occurs.

### Step-by-step flow (sync path, `wrap_model_call`, lines 1003-1122)

1. **Reconstruct effective messages.** `_get_effective_messages` reads
   `_summarization_event` from state and calls `_apply_event_to_messages` to
   build the message list the model would see (summary + preserved tail from the
   prior summarization, if any).

2. **Count tokens once.** `_count_tokens` counts the effective messages, system
   message, and tool schemas. This count is shared between the truncation check
   and the summarization check to avoid redundant computation.

3. **Truncate tool arguments (optional).** If `truncate_args_settings` is configured,
   `_truncate_args` clips large `write_file` / `edit_file` arguments in messages
   before the keep window. This is a lightweight optimization that may reclaim
   enough tokens to avoid full summarization.

4. **Check if summarization is needed.** `_should_summarize` evaluates the trigger
   clauses. If not needed, the handler is called with truncated messages. If the
   handler raises `ContextOverflowError`, the code falls through to summarization
   anyway.

5. **Determine the cutoff index.** `_determine_cutoff_index` (delegated to the
   LangChain helper) decides which messages to keep based on the `keep` policy.

6. **Partition messages.** `_partition_messages` splits the conversation at the
   cutoff into `messages_to_summarize` and `preserved_messages`.

7. **Handle overflow tail clipping.** If triggered by `ContextOverflowError`,
   `_clip_overflow_tail` further shrinks the preserved messages by offloading
   large `ToolMessage` results to per-tool-call files on the backend.

8. **Offload to backend.** `_offload_to_backend` persists the messages being
   summarized as a timestamped markdown section appended to
   `/conversation_history/{thread_id}.md`. Previous summary messages are filtered
   out to avoid redundant storage during chained summarization.

9. **Generate the summary.** `_create_summary` calls the configured LLM with the
   `summary_prompt` to produce a concise summary of the evicted messages.

10. **Build the summary message.** `_build_new_messages_with_path` creates a
    `HumanMessage` containing the summary text and (if offload succeeded) a
    reference to the backend file path.

11. **Compute the state cutoff.** `_compute_state_cutoff` translates the
    effective-list cutoff index to an absolute state index, accounting for any
    prior summarization event.

12. **Call the handler.** The handler is invoked with
    `[summary_message, *preserved_messages]`.

13. **Return an ExtendedModelResponse.** The response wraps the model output plus
    a `Command(update={"_summarization_event": new_event})` that persists the
    summarization event to state.

### The async path

`awrap_model_call` (line 1124) follows the same logic but uses `await` and runs
the offload and summary generation concurrently via `asyncio.gather` (line 1209):

```python
file_path, summary = await asyncio.gather(
    self._aoffload_to_backend(backend, messages_to_summarize),
    self._acreate_summary(messages_to_summarize),
)
```

### What the summary message looks like

When the backend offload succeeds, the summary message content is (lines 546-555):

```
You are in the middle of a conversation that has been summarized.

The full conversation history has been saved to {file_path} should you need
to refer back to it for details.

A condensed summary follows:

<summary>
{summary}
</summary>
```

When offload fails (line 557):

```
Here is a summary of the conversation to date:

{summary}
```

The message is tagged with `additional_kwargs={"lc_source": "summarization"}` so
that subsequent summarization cycles can identify and filter it out of offloads.

---

## 6. Interaction with DeltaChannel and _messages_delta_reducer

### The non-mutating design

A critical design decision in the Deep Agents summarization middleware is that it
**does not modify `state["messages"]`** during normal summarization. This contrasts
with the upstream LangChain middleware, which issues
`RemoveMessage(id=REMOVE_ALL_MESSAGES)` from `before_model` to wipe and replace the
message list.

Instead, Deep Agents tracks summarization via the private `_summarization_event`
state key. The raw message log in `state["messages"]` remains untouched. On each
model call, `_get_effective_messages` reconstructs the effective (summarized) view
by reading the event:

```python
def _get_effective_messages(self, request: ModelRequest) -> list[AnyMessage]:
    event = request.state.get("_summarization_event")
    return self._apply_event_to_messages(request.messages, event)
```

`_apply_event_to_messages` (line 582) builds the effective list as:

```python
result: list[AnyMessage] = [summary_msg]
result.extend(messages[cutoff_idx:])
return result
```

### The REMOVE_ALL_MESSAGES sentinel

The `REMOVE_ALL_MESSAGES` sentinel is imported in `_messages_reducer.py` from
`langgraph.graph.message`. In the `_messages_delta_reducer` (line 31), when a
`RemoveMessage` with `id == REMOVE_ALL_MESSAGES` appears in the writes, it resets
the entire state:

```python
if remove_all_idx is not None:
    state_msgs = []
    msgs = msgs[remove_all_idx + 1 :]
```

The Deep Agents summarization middleware avoids this sentinel entirely. State
updates from summarization only include `_summarization_event` (and optionally
`messages` for tail clipping on overflow). The `messages` channel remains
append-only, which is compatible with `DeltaChannel`'s O(N) checkpoint growth
model (vs. the O(N^2) that full rewrites would cause).

### When messages IS modified

The only case where the summarization middleware writes to `state["messages"]` is
during the `ContextOverflowError` fallback, when `_clip_overflow_tail` offloads
large tool results to per-file backend paths. The clipped `ToolMessage` stubs are
appended as a `new_state_tail` (lines 1115-1116):

```python
update: dict[str, Any] = {"_summarization_event": new_event}
if new_state_tail:
    update["messages"] = list(new_state_tail)
```

---

## 7. Configuration Options and Parameters

### SummarizationMiddleware.__init__ parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str \| BaseChatModel` | (required) | LLM for generating summaries |
| `backend` | `BACKEND_TYPES` | (required) | Backend for persisting conversation history |
| `trigger` | `ContextSize \| TriggerClause \| list[...] \| None` | `None` | Threshold(s) that trigger summarization |
| `keep` | `ContextSize` | `("messages", 20)` | Context retention policy after summarization |
| `token_counter` | `TokenCounter` | `count_tokens_approximately` | Function to count tokens in messages |
| `summary_prompt` | `str` | `DEEPAGENTS_DEFAULT_SUMMARY_PROMPT` | Prompt template for generating summaries |
| `trim_tokens_to_summarize` | `int \| None` | `4000` | Max tokens to include when generating summary |
| `truncate_args_settings` | `TruncateArgsSettings \| None` | `None` | Settings for truncating large tool arguments |

### TruncateArgsSettings fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `trigger` | `ContextSize \| None` | `None` | Threshold that activates truncation; `None` disables |
| `keep` | `ContextSize` | `("messages", 20)` | How many recent messages to leave untouched |
| `max_length` | `int` | `2000` | Character limit per argument value before clipping |
| `truncation_text` | `str` | `"...(argument truncated)"` | Replacement suffix after the first 20 chars |

### SummarizationToolMiddleware.__init__ parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `summarization` | `_DeepAgentsSummarizationMiddleware` | (required) | The engine instance to delegate to |
| `system_prompt` | `str \| None` | `SUMMARIZATION_SYSTEM_PROMPT` | System-prompt nudge for the compact tool; `None` skips it |

### create_summarization_middleware parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `BaseChatModel` | (required) | Resolved chat model instance |
| `backend` | `BACKEND_TYPES` | (required) | Backend for persisting history |
| `summary_prompt` | `str` | `DEEPAGENTS_DEFAULT_SUMMARY_PROMPT` | Prompt template for summaries |
| `trim_tokens_to_summarize` | `int \| None` | `None` | Max tokens for summary generation |
| `token_counter` | `TokenCounter` | `count_tokens_approximately` | Token counting function |

### create_summarization_tool_middleware parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str \| BaseChatModel` | (required) | Chat model instance or model string |
| `backend` | `BACKEND_TYPES` | (required) | Backend for persisting history |
| `system_prompt` | `str \| None` | `SUMMARIZATION_SYSTEM_PROMPT` | System-prompt nudge for the compact tool |

---

## 8. State Management -- SummarizationState

### SummarizationState definition (line 170)

```python
class SummarizationState(AgentState):
    _summarization_event: Annotated[
        NotRequired[SummarizationEvent | None],
        PrivateStateAttr,
    ]
```

The leading underscore and `PrivateStateAttr` annotation mark this as a private
state field. It is not exposed to the model and is not visible in the public API.
Both `SummarizationMiddleware` and `SummarizationToolMiddleware` declare
`state_schema = SummarizationState` so the framework merges the field into the
agent's composite state.

### SummarizationEvent definition (line 113)

```python
class SummarizationEvent(TypedDict):
    cutoff_index: int
    summary_message: HumanMessage
    file_path: str | None
```

- `cutoff_index`: The absolute index in `state["messages"]` where summarization
  occurred. All messages before this index have been summarized. This is the
  **state-level** index, not the effective-message-list index.
- `summary_message`: The `HumanMessage` containing the summary text, tagged with
  `additional_kwargs={"lc_source": "summarization"}`.
- `file_path`: The backend path where the conversation history was offloaded, or
  `None` if the offload failed.

### Cutoff index arithmetic

When chained summarization occurs (a second summarization after a prior one), the
effective message list starts with the summary message at index 0, followed by
messages from `cutoff_index` onward. The `_compute_state_cutoff` method (line 622)
translates between effective-list indices and state-level indices:

```python
@staticmethod
def _compute_state_cutoff(
    event: SummarizationEvent | None,
    effective_cutoff: int,
) -> int:
    if event is None:
        return effective_cutoff
    prior_cutoff = event.get("cutoff_index")
    if not isinstance(prior_cutoff, int):
        logger.warning("Malformed _summarization_event: missing cutoff_index")
        return effective_cutoff
    return prior_cutoff + effective_cutoff - 1
```

The `-1` accounts for the summary message at effective index 0, which does not
correspond to a real state message.

---

## 9. Tool-Argument Truncation

Before full summarization is considered, the middleware can apply a lighter-weight
optimization: truncating large string arguments in old `AIMessage.tool_calls`.

### Which tool calls are targeted

Only `write_file` and `edit_file` tool calls are truncated (line 832):

```python
if tool_call["name"] in {"write_file", "edit_file"}:
    truncated_call = self._truncate_tool_call(tool_call)
```

### How truncation works

The `_truncate_tool_call` method (line 728) iterates over the tool call's `args`
dictionary. For each string value exceeding `max_length` (default 2000 characters),
it replaces it with the first 20 characters followed by the `truncation_text`
(default `"...(argument truncated)"`):

```python
if isinstance(value, str) and len(value) > self._max_arg_length:
    truncated_args[key] = value[:20] + self._truncation_text
```

### Cutoff determination for truncation

`_determine_truncate_cutoff_index` (line 679) supports three keep policies:

- `"messages"`: Preserves the last N messages without truncation.
- `"tokens"`: Preserves recent messages up to a token budget, counting backwards.
- `"fraction"`: Like tokens, but the budget is a fraction of `max_input_tokens`.

Messages at indices before the cutoff have their tool args truncated; messages at
or after the cutoff are left intact.

---

## 10. The compact_conversation Tool

### Tool creation (line 1499)

`SummarizationToolMiddleware._create_compact_tool` creates a `StructuredTool` with
both sync and async implementations:

```python
return StructuredTool.from_function(
    name="compact_conversation",
    description=(
        "Compact the conversation by summarizing older messages "
        "into a concise summary. Use this proactively when the "
        "conversation is getting long to free up context window "
        "space. This tool takes no arguments."
    ),
    func=sync_compact,
    coroutine=async_compact,
)
```

The tool takes no arguments (the input schema is `CompactConversationSchema`, an
empty `BaseModel`).

### Eligibility gating

To prevent premature compaction, the tool checks `_is_eligible_for_compaction`
(line 1657) before proceeding. The conversation must be at or above approximately
50% of the configured auto-summarization trigger:

```python
@staticmethod
def _compact_threshold(value: float) -> int:
    return max(1, int(value * 0.5))
```

- For `("tokens", N)`, eligibility starts at `0.5 * N` tokens.
- For `("messages", N)`, eligibility starts at `0.5 * N` messages.
- For `("fraction", F)`, eligibility starts at `0.5 * F` of `max_input_tokens`.
- For dict clauses, all specified thresholds must be met (AND semantics).

If ineligible, the tool returns a `ToolMessage`:
```
Nothing to compact yet -- conversation is within the token budget.
```

### System-prompt nudge

`SummarizationToolMiddleware.wrap_model_call` (line 1745) appends the
`SUMMARIZATION_SYSTEM_PROMPT` to the system message on every model call:

```python
SUMMARIZATION_SYSTEM_PROMPT = """## Compact conversation Tool `compact_conversation`

You have access to a `compact_conversation` tool. This tool refreshes your
context window to reduce context bloat and costs.

You should use the tool when:
- The user asks to move on to a completely new task for which previous context
  is likely irrelevant.
- You have finished extracting or synthesizing a result and previous working
  context is no longer needed.
"""
```

Pass `system_prompt=None` to suppress this nudge.

### Compact tool execution flow (sync, line 1677)

1. Read `messages` and `_summarization_event` from `runtime.state`.
2. Reconstruct effective messages via `_apply_event_to_messages`.
3. Check eligibility via `_is_eligible_for_compaction`. If ineligible, return
   "nothing to compact" `ToolMessage`.
4. Determine cutoff index. If 0, return "nothing to compact".
5. Partition messages, generate summary, offload to backend.
6. Build and return a `Command` that updates `_summarization_event` and appends
   a confirmation `ToolMessage`:
   ```
   Conversation compacted. Summarized {N} messages into a concise summary.
   ```

### Error handling in the compact tool

If any step in the compact flow raises an exception, it is caught (line 1705):

```python
except Exception as exc:
    logger.exception("compact_conversation tool failed")
    return self._compact_error(tool_call_id, exc)
```

The error is returned as a `ToolMessage` rather than raised, because tool execution
must always return a message to the agent:

```
Compaction failed: an error occurred while generating the summary
({ExceptionType}: {message}). The conversation has not been compacted
-- no messages were summarized or removed.
```

---

## 11. Backend Offload

### Storage layout

Evicted messages are stored as markdown at:
```
{artifacts_root}/conversation_history/{thread_id}.md
```

Each summarization event appends a new section with a UTC timestamp header:

The format of each appended section (from `_offload_to_backend`, line 882):

```python
new_section = f"## Summarized at {timestamp}\n\n{get_buffer_string(filtered_messages)}\n\n"
```

Where `timestamp` is a UTC ISO-8601 string, and `get_buffer_string` converts the
message list to a human-readable buffer string.

### Thread ID resolution

The `_get_thread_id` method (line 466) extracts the thread ID from the LangGraph
config via `get_config()`. If no thread ID is available (e.g., outside a runnable
context), it falls back to a generated session ID:

```python
generated_id = f"session_{uuid.uuid4().hex[:8]}"
```

### Offload mechanics (sync, line 853)

1. Compute the file path: `{history_path_prefix}/{thread_id}.md`.
2. Filter out previous summary messages (to avoid redundant storage during chained
   summarization).
3. Read existing content from the backend via `download_files()` (not `read()`,
   because `read()` returns line-numbered content intended for LLM consumption).
4. Append the new section to the existing content.
5. Write the combined content back via `edit()` (if content existed) or `write()`
   (for new files).
6. Return the file path on success, or `None` on failure.

### Offload failure handling

Backend offload failure is non-fatal. If offload fails:
- The file path is `None`.
- A warning is logged and emitted via `warnings.warn`.
- The summary message omits the file-path reference.
- Summarization still proceeds -- the agent loses the ability to retrieve the
  original messages but continues operating.

### Overflow tail clipping

When `ContextOverflowError` triggers summarization, the preserved messages may
themselves be too large. The `_clip_overflow_tail` function (from
`_overflow_clip.py`) handles this by:

1. Identifying the trailing batch of consecutive `ToolMessage` objects.
2. For `read_file` tool results: head-slicing the content to approximately 4000
   characters and appending a pointer to the original file path.
3. For other large tool results: offloading the full content to
   `{large_tool_results_prefix}/{tool_call_id}` on the backend, then replacing
   the message with a stub.

---

## 12. Edge Cases and Error Handling

### Malformed summarization events

`_apply_event_to_messages` (line 599) defensively handles malformed events:

```python
try:
    summary_msg = event["summary_message"]
    cutoff_idx = event["cutoff_index"]
except (KeyError, TypeError) as exc:
    logger.warning("Malformed _summarization_event (missing keys): %s", exc)
    return list(messages)
```

If the event is missing required keys, the method falls back to returning the
full message list unmodified, logged as a warning.

### Out-of-bounds cutoff index

If `cutoff_index` exceeds the message count (line 609):

```python
if cutoff_idx > len(messages):
    logger.warning(
        "Summarization cutoff_index %d exceeds message count %d; "
        "remaining slice will be empty",
        cutoff_idx,
        len(messages),
    )
    return [summary_msg]
```

The result is the summary message alone, with no preserved tail.

### Zero cutoff index

If `_determine_cutoff_index` returns 0 (line 1067), meaning no messages can be
summarized (all messages are within the keep window), summarization is skipped
and the handler is called with the current messages.

### ContextOverflowError fallback

The `wrap_model_call` method (lines 1058-1063) catches `ContextOverflowError` from
the model call:

```python
if not should_summarize:
    try:
        return handler(request.override(messages=truncated_messages))
    except ContextOverflowError:
        overflow_triggered = True
```

When triggered, the middleware falls through to the summarization path. This is
a safety net: even if the trigger thresholds are set too high (or the model's
`max_input_tokens` profile is wrong), the middleware will still attempt to recover.

### Summary message identification

The `_is_summary_message` method (line 501) identifies previous summary messages by
checking for `additional_kwargs.get("lc_source") == "summarization"` on
`HumanMessage` instances. This prevents double-storage during chained
summarization: when a second summarization occurs, the prior summary message is
filtered from the offload.

### Backend factory resolution

The `_get_backend` method (line 434) handles both instance and factory backends.
When the backend is callable (a factory function), it constructs a `ToolRuntime`
from the runtime context:

```python
if callable(self._backend):
    config = cast("RunnableConfig", getattr(runtime, "config", {}))
    tool_runtime = ToolRuntime(
        state=state,
        context=runtime.context,
        stream_writer=runtime.stream_writer,
        store=runtime.store,
        config=config,
        tool_call_id=None,
    )
    return _resolve_backend(self._backend, tool_runtime)
return self._backend
```

### Deprecated `history_path_prefix` parameter

The `__init__` method (line 341) handles the deprecated `history_path_prefix`
keyword argument:

```python
_deprecated_history_prefix = deprecated_kwargs.pop("history_path_prefix", None)
if _deprecated_history_prefix is not None:
    warn_deprecated(
        since="0.5.0",
        removal="0.7.0",
        message=(
            "The argument `history_path_prefix` is deprecated and "
            "will be removed in deepagents==0.7.0. Use "
            "`CompositeBackend(artifacts_root='/my/root', ...)` instead."
        ),
        package="deepagents",
    )
```

### Type validation in SummarizationToolMiddleware

The `__init__` of `SummarizationToolMiddleware` (line 1478) validates the
`system_prompt` type:

```python
if system_prompt is not None and not isinstance(system_prompt, str):
    msg = f"system_prompt must be str or None, got {type(system_prompt).__name__}"
    raise TypeError(msg)
```

### Type validation in create_summarization_middleware

The factory (line 1313) validates the model type at runtime:

```python
if not isinstance(model, RuntimeBaseChatModel):
    msg = "`create_summarization_middleware` expects `model` to be a `BaseChatModel` instance."
    raise TypeError(msg)
```

---

## 13. Integration with the Middleware Stack

### Full stack ordering

The complete middleware ordering in `create_deep_agent` (from `graph.py`,
lines 331-354) is:

```
Base stack (always present):
  1.  TodoListMiddleware
  2.  SkillsMiddleware (conditional)
  3.  FilesystemMiddleware
  4.  SubAgentMiddleware (conditional)
  5.  SummarizationMiddleware
  6.  PatchToolCallsMiddleware
  7.  AsyncSubAgentMiddleware (conditional)

User middleware slot (from middleware= parameter):
  8+. Any user-supplied middleware (including SummarizationToolMiddleware)

Tail stack:
  N-4. Harness profile extra_middleware
  N-3. _ToolExclusionMiddleware (conditional)
  N-2. AnthropicPromptCachingMiddleware
  N-1. MemoryMiddleware (conditional)
  N.   HumanInTheLoopMiddleware (conditional)
```

### Excludability

`SummarizationMiddleware` is excludable -- it is not in the `_REQUIRED_MIDDLEWARE`
set. It can be excluded via:

```python
# In harness profile
excluded_middleware={"SummarizationMiddleware"}
```

The `name` property (line 270) returns `"SummarizationMiddleware"` for the core
class (despite the internal class name being `_DeepAgentsSummarizationMiddleware`):

```python
@property
def name(self) -> str:
    if type(self) is _DeepAgentsSummarizationMiddleware:
        return "SummarizationMiddleware"
    return type(self).__name__
```

The `serialized_name` class variable is also set to `"SummarizationMiddleware"` for
config-file exclusion export.

### Interaction with other middleware

- **FilesystemMiddleware**: Provides the `read_file` tool that the agent uses to
  retrieve offloaded conversation history referenced in the summary message.

- **PatchToolCallsMiddleware**: Runs after summarization. Its position ensures
  tool-call patching operates on the already-summarized message list.

- **AnthropicPromptCachingMiddleware**: Runs after user middleware in the tail
  stack. The summarization system's modifications to the system message (via
  `SummarizationToolMiddleware`) are finalized before cache-control breakpoints
  are applied.

- **MemoryMiddleware**: Runs after prompt caching. Since summarization may change
  the system prompt (via the compact tool nudge), this ordering ensures memory
  updates do not invalidate the Anthropic prompt cache prefix.

### State schema composition

The `DeepAgentState` base class (from `graph.py`, line 64) uses a `DeltaChannel`
reducer on messages:

```python
class DeepAgentState(AgentState):
    messages: Required[Annotated[
        list[AnyMessage],
        DeltaChannel(_messages_delta_reducer, snapshot_frequency=50),
    ]]
```

`SummarizationState` extends `AgentState` (not `DeepAgentState` directly) with the
`_summarization_event` field. The framework's state-schema merging combines both
schemas so the final agent state has both the `DeltaChannel`-backed `messages` and
the private `_summarization_event` field.

---

## 14. Key Constants and Imports

### Constants defined in this module

| Constant | Line | Value |
|----------|------|-------|
| `SUMMARIZATION_SYSTEM_PROMPT` | 103 | Multi-line string with compact tool usage guidance |

### Constants imported from LangChain

| Constant | Source | Default Value |
|----------|--------|---------------|
| `_DEFAULT_MESSAGES_TO_KEEP` | `langchain.agents.middleware.summarization` | `20` |
| `_DEFAULT_TRIM_TOKEN_LIMIT` | `langchain.agents.middleware.summarization` | `4000` |
| `DEFAULT_SUMMARY_PROMPT` | `langchain.agents.middleware.summarization` | LangChain's default summary prompt template |

### Key imports

```python
from langchain.agents.middleware.summarization import (
    _DEFAULT_MESSAGES_TO_KEEP,
    _DEFAULT_TRIM_TOKEN_LIMIT,
    DEFAULT_SUMMARY_PROMPT,
    ContextSize,
    SummarizationMiddleware as LCSummarizationMiddleware,
    TokenCounter,
)
from langchain.agents.middleware.types import (
    AgentMiddleware, AgentState, ExtendedModelResponse, PrivateStateAttr,
)
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import (
    AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolCall,
    ToolMessage, get_buffer_string,
)
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.types import Command
```

---

## 15. Public API Summary

### Exported names

| Name | Type | Description |
|------|------|-------------|
| `SummarizationMiddleware` | Class alias | Auto-summarization engine (alias for `_DeepAgentsSummarizationMiddleware`) |
| `SummarizationToolMiddleware` | Class | Compact tool provider middleware |
| `SummarizationState` | TypedDict | State schema with `_summarization_event` |
| `SummarizationEvent` | TypedDict | Single summarization event record |
| `TriggerClause` | TypedDict | AND-semantics trigger condition |
| `TruncateArgsSettings` | TypedDict | Tool-argument truncation configuration |
| `SummarizationDefaults` | TypedDict | Model-profile-derived default settings |
| `CompactConversationSchema` | BaseModel | Empty schema for the compact tool |
| `SUMMARIZATION_SYSTEM_PROMPT` | str | System-prompt nudge for the compact tool |
| `compute_summarization_defaults` | function | Compute defaults from model profile |
| `create_summarization_middleware` | function | Factory for `SummarizationMiddleware` |
| `create_summarization_tool_middleware` | function | Factory for both middleware layers |

### Usage example

```python
from deepagents import create_deep_agent
from deepagents.middleware.summarization import (
    SummarizationMiddleware,
    SummarizationToolMiddleware,
)
from deepagents.backends import FilesystemBackend

backend = FilesystemBackend(root_dir="/data")

summ = SummarizationMiddleware(
    model="gpt-5.4-mini",
    backend=backend,
    trigger=("fraction", 0.85),
    keep=("fraction", 0.10),
)
tool_mw = SummarizationToolMiddleware(summ)

agent = create_deep_agent(middleware=[summ, tool_mw])
```

---

## 16. Method Reference

### _DeepAgentsSummarizationMiddleware methods

| Method | Line | Sync/Async | Description |
|--------|------|------------|-------------|
| `__init__` | 284 | -- | Constructor with backend and trigger configuration |
| `model` (property) | 397 | -- | Returns the LLM used for summaries |
| `token_counter` (property) | 402 | -- | Returns the token counting function |
| `name` (property) | 270 | -- | Returns `"SummarizationMiddleware"` for the core class |
| `_get_profile_limits` | 406 | sync | Retrieves `max_input_tokens` from model profile |
| `_should_summarize` | 410 | sync | Checks if summarization thresholds are met |
| `_determine_cutoff_index` | 414 | sync | Computes where to split messages |
| `_partition_messages` | 418 | sync | Splits messages into summarize/preserve sets |
| `_create_summary` | 426 | sync | Generates LLM summary of messages |
| `_acreate_summary` | 430 | async | Async variant of `_create_summary` |
| `_get_backend` | 434 | sync | Resolves backend from instance or factory |
| `_get_thread_id` | 466 | sync | Extracts thread ID from LangGraph config |
| `_get_history_path` | 490 | sync | Generates backend storage path |
| `_is_summary_message` | 501 | sync | Checks if a message is a prior summary |
| `_filter_summary_messages` | 518 | sync | Removes prior summaries from a message list |
| `_build_new_messages_with_path` | 533 | sync | Constructs the summary `HumanMessage` |
| `_get_effective_messages` | 566 | sync | Reconstructs the effective message list |
| `_apply_event_to_messages` | 582 | static | Builds effective messages from event |
| `_compute_state_cutoff` | 622 | static | Translates effective to state cutoff index |
| `_should_truncate_args` | 649 | sync | Checks if arg truncation should fire |
| `_determine_truncate_cutoff_index` | 679 | sync | Computes truncation cutoff |
| `_truncate_tool_call` | 728 | sync | Truncates a single tool call's arguments |
| `_count_tokens` | 756 | sync | Counts tokens including system message and tools |
| `_truncate_args` | 796 | sync | Truncates tool args in old messages |
| `_offload_to_backend` | 853 | sync | Persists evicted messages to backend |
| `_aoffload_to_backend` | 927 | async | Async variant of `_offload_to_backend` |
| `wrap_model_call` | 1003 | sync | Main entry point: truncate, check, summarize, call |
| `awrap_model_call` | 1124 | async | Async variant of `wrap_model_call` |

### SummarizationToolMiddleware methods

| Method | Line | Sync/Async | Description |
|--------|------|------------|-------------|
| `__init__` | 1458 | -- | Constructor with summarization engine and system prompt |
| `_resolve_backend` | 1485 | sync | Resolves backend via `ToolRuntime` |
| `_create_compact_tool` | 1499 | sync | Creates the `compact_conversation` StructuredTool |
| `_build_compact_result` | 1529 | sync | Builds the `Command` for a successful compact |
| `_nothing_to_compact` | 1577 | static | Returns "nothing to compact" `ToolMessage` |
| `_compact_error` | 1598 | static | Returns error `ToolMessage` |
| `_compact_threshold` | 1626 | static | Computes 50% of a trigger value |
| `_compact_trigger_clause` | 1630 | static | Normalizes trigger conditions |
| `_is_compaction_clause_met` | 1638 | sync | Checks a single eligibility clause |
| `_is_eligible_for_compaction` | 1657 | sync | Checks overall eligibility (OR over clauses) |
| `_run_compact` | 1677 | sync | Sync compact tool implementation |
| `_arun_compact` | 1711 | async | Async compact tool implementation |
| `wrap_model_call` | 1745 | sync | Injects system-prompt nudge |
| `awrap_model_call` | 1768 | async | Async variant of `wrap_model_call` |