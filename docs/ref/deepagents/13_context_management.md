# 13 -- Context Management Middleware

> Primary sources:
> `libs/deepagents/deepagents/middleware/summarization.py` (1790 lines)
> `libs/deepagents/deepagents/middleware/_message_eviction.py` (163 lines)
> `libs/deepagents/deepagents/middleware/_overflow_clip.py` (207 lines)
> Upstream base: `langchain.agents.middleware.summarization.SummarizationMiddleware`

---

## 1. Overview

Long-running agents accumulate conversation history that eventually exceeds the model's context window. Deep Agents manages this with three cooperating mechanisms, listed here in the order they engage:

| Layer | Module | Fires When | Strategy |
|-------|--------|-----------|----------|
| Tool-argument truncation | `summarization.py` | Configurable threshold (default 85%) | Clips `write_file`/`edit_file` args in old messages |
| Summarization | `summarization.py` | Configurable threshold (default 85%) | LLM-generated summary replaces old messages |
| Message eviction | `_message_eviction.py` | Per-tool-result, by `FilesystemMiddleware` | Offloads large tool results to backend files |
| Overflow clip | `_overflow_clip.py` | `ContextOverflowError` from provider | Last-resort tail clipping after summarization |

These are not independent middleware classes. `SummarizationMiddleware` orchestrates all of them from its `wrap_model_call` hook, calling into the eviction and clip helpers as needed.

---

## 2. Summarization Middleware

### 2.1 Class Hierarchy

The public class is `SummarizationMiddleware`, an alias for `_DeepAgentsSummarizationMiddleware`. It wraps LangChain's `langchain.agents.middleware.summarization.SummarizationMiddleware` (referred to as `LCSummarizationMiddleware`) to add behavior that long-running, file-aware agents need.

```python
from deepagents.middleware.summarization import SummarizationMiddleware
from deepagents.middleware import SummarizationMiddleware  # same thing
```

### 2.2 What Deep Agents Adds Over LangChain

LangChain's base middleware operates via `before_model`, rewriting `state["messages"]` with a `RemoveMessage(id=REMOVE_ALL_MESSAGES)` sentinel followed by the summary and preserved messages. Deep Agents replaces this entirely:

1. **Backend offload.** Evicted messages are appended to `/conversation_history/{thread_id}.md` on the backend. The summary embeds the path so the agent can `read_file` it.

2. **Pre-summarization arg truncation.** Large `write_file`/`edit_file` arguments in older messages are clipped, often reclaiming enough context to skip summarization.

3. **`ContextOverflowError` fallback.** On provider over-budget rejection, the middleware summarizes and retries.

4. **Non-mutating state.** Summarization is tracked in a private `_summarization_event` field via `wrap_model_call`. The raw `state["messages"]` is never rewritten.

5. **Auto-selected thresholds.** `compute_summarization_defaults` picks fraction-based defaults from the model profile when `max_input_tokens` is available.

### 2.3 Constructor

```python
SummarizationMiddleware(
    model="gpt-5.4-mini",
    backend=backend,
    trigger=("fraction", 0.85),
    keep=("fraction", 0.10),
    token_counter=count_tokens_approximately,
    summary_prompt=DEEPAGENTS_DEFAULT_SUMMARY_PROMPT,
    trim_tokens_to_summarize=4000,
    truncate_args_settings={"trigger": ("fraction", 0.85), "keep": ("fraction", 0.10)},
)
```

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `model` | `str` or `BaseChatModel` | required | Model for generating summaries |
| `backend` | `BACKEND_TYPES` | required | Backend for persisting evicted history |
| `trigger` | `ContextSize` / `TriggerClause` / `list` | `None` | When to trigger summarization |
| `keep` | `ContextSize` | `("messages", 20)` | How much recent context to preserve |
| `token_counter` | `TokenCounter` | `count_tokens_approximately` | Token counting function |
| `summary_prompt` | `str` | `DEEPAGENTS_DEFAULT_SUMMARY_PROMPT` | Prompt for summarization call |
| `trim_tokens_to_summarize` | `int` or `None` | `4000` | Max tokens fed to summarization model |
| `truncate_args_settings` | `TruncateArgsSettings` or `None` | `None` | Arg truncation config |

### 2.4 Trigger Configuration

Three forms of `ContextSize`:

```python
("tokens", 170000)    # absolute token count
("fraction", 0.85)    # fraction of model's max_input_tokens
("messages", 100)     # absolute message count
```

A list uses **OR** semantics (any match triggers). A `TriggerClause` dict uses **AND** semantics (all must match):

```python
trigger=[("fraction", 0.85), ("messages", 100)]   # OR
trigger={"tokens": 100000, "messages": 50}         # AND
```

The `_should_summarize` method evaluates triggers against two signals: the approximate token count from `token_counter`, and the reported `total_tokens` from the most recent `AIMessage.usage_metadata`.

### 2.5 Keep / Retention Policy

```python
keep=("messages", 20)    # Keep the 20 most recent messages
keep=("tokens", 50000)   # Keep messages totaling ~50k tokens
keep=("fraction", 0.10)  # Keep 10% of model's context window
```

The `_determine_cutoff_index` method computes the partition point using binary search for token/fraction-based retention. After computing the raw cutoff, `_find_safe_cutoff_point` ensures it does not split an AIMessage from its corresponding ToolMessages by searching backward for the matching AIMessage.

### 2.6 Model-Aware Defaults

`compute_summarization_defaults` inspects the model profile:

With `max_input_tokens` available:
```python
{"trigger": ("fraction", 0.85), "keep": ("fraction", 0.10),
 "truncate_args_settings": {"trigger": ("fraction", 0.85), "keep": ("fraction", 0.10)}}
```

Without profile (conservative fallback):
```python
{"trigger": ("tokens", 170000), "keep": ("messages", 6),
 "truncate_args_settings": {"trigger": ("messages", 20), "keep": ("messages", 20)}}
```

### 2.7 Tool-Argument Truncation

A lighter-weight optimization that runs before full summarization. Truncates large `args` on `AIMessage.tool_calls` in older messages, targeting `write_file` and `edit_file` calls.

```python
class TruncateArgsSettings(TypedDict, total=False):
    trigger: ContextSize | None   # threshold to activate truncation
    keep: ContextSize             # recent messages to leave untouched
    max_length: int               # char limit per argument (default 2000)
    truncation_text: str          # suffix for truncated args
```

When truncation fires, each argument string exceeding `max_length` is replaced with its first 20 characters followed by `truncation_text`. Only `write_file` and `edit_file` tool calls are candidates.

### 2.8 The Summarization Prompt

The default `DEEPAGENTS_DEFAULT_SUMMARY_PROMPT` (which augments LangChain's `DEFAULT_SUMMARY_PROMPT` with a media-tag addendum) asks the model to extract context under four sections: SESSION INTENT (the user's goal), SUMMARY (important choices and reasoning), ARTIFACTS (files created/modified with paths), and NEXT STEPS (remaining tasks). Messages are trimmed to `trim_tokens_to_summarize` tokens before being sent.

### 2.9 The `wrap_model_call` Control Flow

```
1. Reconstruct effective messages from state + _summarization_event
2. Count tokens once (expensive due to tool-schema conversion)
3. Attempt tool-argument truncation
4. Re-count tokens if truncation modified messages
5. Check if summarization should trigger
   |
   +-- NO:  Call model with truncated messages
   |        If ContextOverflowError -> set overflow_triggered, continue
   |
   +-- YES (or overflow_triggered):
       a. Compute cutoff index
       b. Partition into [to_summarize | preserved]
       c. If overflow: clip preserved tail via _clip_overflow_tail
       d. Offload to_summarize to backend
       e. Generate LLM summary
       f. Build summary HumanMessage with backend path
       g. Call model with [summary_msg | preserved]
       h. Return ExtendedModelResponse with _summarization_event update
```

In the async path, backend offload and summary generation run concurrently:

```python
file_path, summary = await asyncio.gather(
    self._aoffload_to_backend(backend, messages_to_summarize),
    self._acreate_summary(messages_to_summarize),
)
```

### 2.10 State Tracking via `_summarization_event`

The middleware stores a `SummarizationEvent` in a private state field:

```python
class SummarizationEvent(TypedDict):
    cutoff_index: int               # absolute index into state messages
    summary_message: HumanMessage   # the summary with backend path
    file_path: str | None           # backend path, or None if offload failed
```

On subsequent calls, `_get_effective_messages` reconstructs what the model sees: `[summary_message] + state["messages"][cutoff_index:]`. The raw `state["messages"]` retains full history for replay and evals.

For chained summarizations, `_compute_state_cutoff` translates the new effective-list cutoff back to an absolute state index: `event["cutoff_index"] + effective_cutoff - 1`. The `-1` accounts for the summary message at effective index 0.

### 2.11 Backend Offloading

Evicted messages are persisted as markdown at `/conversation_history/{thread_id}.md`. Each summarization event appends a timestamped section. The `thread_id` comes from the LangGraph config via `get_config()`, with a generated `session_*` fallback.

Previous summary messages (identified by `lc_source: "summarization"` in `additional_kwargs`) are filtered before offloading to avoid redundant storage.

The summary message presented to the model includes the backend path so the agent can recover context:

```
You are in the middle of a conversation that has been summarized.
The full conversation history has been saved to /conversation_history/abc123.md
should you need to refer back to it for details.

A condensed summary follows:
<summary>...</summary>
```

If the backend offload fails, summarization still proceeds but the path reference is omitted.

### 2.12 The `SummarizationToolMiddleware`

The `compact_conversation` tool lets the agent trigger compaction on demand. It composes with a `SummarizationMiddleware` instance and reuses its summarization engine.

```python
from deepagents.middleware.summarization import (
    SummarizationMiddleware, SummarizationToolMiddleware,
)
summ = SummarizationMiddleware(model="gpt-5.4-mini", backend=backend)
tool_mw = SummarizationToolMiddleware(summ)
agent = create_deep_agent(middleware=[summ, tool_mw])
```

The tool is gated by `_is_eligible_for_compaction`, requiring approximately 50% of the auto-summarization trigger to be reached. A system prompt nudge is injected via `wrap_model_call`. The convenience factory `create_summarization_tool_middleware` creates both layers in a single call.

### 2.13 Token Counting

The `_count_tokens` method inspects the configured `token_counter` signature once at construction to determine whether it accepts a `tools` keyword. This avoids per-call introspection. The token count is computed once and shared between truncation and summarization checks.

---

## 3. Message Eviction

### 3.1 Purpose

`_message_eviction.py` provides shared helpers for evicting large message content. It is used by `FilesystemMiddleware` (proactive per-tool-call offload when results exceed a threshold) and by the overflow clip path (reactive clipping after `ContextOverflowError`). This module is not a standalone middleware class.

### 3.2 Content Preview

When a large tool result is offloaded, the replacement includes a head+tail preview:

```python
def _create_content_preview(content_str, *, head_lines=5, tail_lines=5):
    lines = content_str.splitlines()
    if len(lines) <= head_lines + tail_lines:
        return format_content_with_line_numbers(lines, start_line=1)
    head = [line[:1000] for line in lines[:head_lines]]
    tail = [line[:1000] for line in lines[-tail_lines:]]
    # head_sample + "... [N lines truncated] ..." + tail_sample
```

Each preview line is capped at 1000 characters.

### 3.3 Text Extraction

`_extract_text_from_message` handles both string and list-of-blocks content. For list content, it joins all `text` type blocks and ignores non-text blocks (images, media). This provides the text to be offloaded while preserving multimodal content in the conversation.

### 3.4 Offloading a Tool Message

The core function `_offload_tool_message_content` writes content to a backend path derived from the tool call ID:

```python
def _offload_tool_message_content(
    message: ToolMessage, content_str: str,
    backend: BackendProtocol, large_tool_results_prefix: str,
) -> ToolMessage | None:
```

Flow: sanitize the `tool_call_id` for use as a filename, write to `{prefix}/{sanitized_id}`, build a replacement ToolMessage with the `TOO_LARGE_TOOL_MSG` template containing the preview and file path. Returns `None` if the backend write fails.

The `TOO_LARGE_TOOL_MSG` template tells the agent where to find the full result:

```
Tool result too large, the result of this tool call {tool_call_id}
was saved in the filesystem at this path: {file_path}
You can read the result from the filesystem by using the read_file tool,
but make sure to only read part of the result at a time.
```

### 3.5 Preserving Non-Text Content

`_build_evicted_content` handles mixed content types (text + images). For list content with non-text blocks, it replaces all text blocks with a single replacement block while preserving media blocks. `_build_evicted_tool_message` preserves identity fields (`tool_call_id`, `name`, `id`, `artifact`, `status`) so the messages reducer can match and overwrite the original.

### 3.6 Async Variant

`_aoffload_tool_message_content` is the async counterpart, using `await backend.awrite()` for non-blocking backend writes. The API is otherwise identical to the sync version.

---

## 4. Overflow Clip

### 4.1 Purpose

`_overflow_clip.py` is the last-resort safety mechanism. When `SummarizationMiddleware.wrap_model_call` catches a `ContextOverflowError`, it summarizes **and** invokes `_clip_overflow_tail` to shrink the trailing ToolMessage batch in the preserved suffix. This fires only when summarization alone still leaves too much content.

### 4.2 Activation Sequence

1. `wrap_model_call` attempts the model call.
2. Provider raises `ContextOverflowError`.
3. Middleware falls back to summarization.
4. During summarization, `_clip_overflow_tail` clips the preserved tail.

### 4.3 Threshold Derivation

```python
def _derive_overflow_clip_threshold_tokens(keep, max_input_tokens):
    kind, value = keep
    if kind == "tokens":   return int(value)
    if kind == "fraction":
        return int(max_input_tokens * value) if max_input_tokens else 5_000
    return 5_000  # fallback for message-based keep
```

The clip only engages when the tail ToolMessage batch exceeds this threshold.

### 4.4 Tail Batch Detection

`_find_tail_tool_message_batch` scans backward from the end of `preserved_messages` to find consecutive ToolMessages. If the preserved messages do not end with ToolMessages, clipping is skipped entirely.

### 4.5 Per-Message Clipping Strategy

Each ToolMessage in the tail is clipped via `_clip_one_tail_message`, which applies one of two strategies based on the tool that produced the result:

**read_file results:** Content is sliced to approximately 4000 characters with a notice pointing back to the original `file_path`. No new backend write is needed because the file already exists.

```python
def _slice_read_file_tm(msg, original_path):
    content = _extract_text_from_message(msg)
    notice = f"[Output truncated. Full content at {original_path}. ...]"
    return msg.model_copy(update={"content": content[:4_000] + notice})
```

**All other tool results:** Full content is offloaded to `/large_tool_results/{tool_call_id}` via `_offload_tool_message_content`, replaced with a `TOO_LARGE_TOOL_MSG` stub.

`_build_tool_call_index` maps each `tool_call_id` to its originating `tool_call` dict from AIMessages, so the clipper knows which tool name produced each result.

### 4.6 Return Values

`_clip_overflow_tail` returns a tuple `(modified_preserved_messages, replacement_tool_messages)`. The replacements carry original message `id` values so the `add_messages` reducer overwrites the originals when propagated via a `Command` update.

### 4.7 Async Concurrency

The async variant `_aclip_overflow_tail` clips all tail ToolMessages concurrently via `asyncio.gather`, which is beneficial when multiple large results need simultaneous offloading:

```python
results = await asyncio.gather(
    *[_aclip_one_tail_message(msg, ...) for msg in tail_batch]
)
```

---

## 5. How The Three Layers Interact

### 5.1 Ordering Within `wrap_model_call`

The three mechanisms execute as phases within a single `wrap_model_call`:

```
Phase 1: Tool-argument truncation (_truncate_args)
Phase 2: Threshold check (_should_summarize)
   +-- Below threshold: call model directly
   |     +-- ContextOverflowError? -> Phase 3
   +-- Above threshold: Phase 3
Phase 3: Summarization + Overflow clip
   a. Partition messages
   b. If overflow: _clip_overflow_tail on preserved tail
   c. _offload_to_backend on messages to summarize
   d. _create_summary via LLM
   e. Retry model call with compacted messages
```

### 5.2 Message Eviction Is Separate

`FilesystemMiddleware` calls message eviction proactively in its `wrap_tool_call` hook -- after each tool execution, any result exceeding the size threshold is immediately offloaded. This operates independently of summarization and runs on every tool call, not just when context pressure builds. The eviction helpers are stateless utility functions shared between this proactive path and the reactive overflow path.

### 5.3 Escalation Path

1. **Proactive eviction** (FilesystemMiddleware): Individual large tool results offloaded immediately after tool execution.
2. **Argument truncation** (SummarizationMiddleware): Old `write_file`/`edit_file` args clipped when context nears the trigger threshold. Often delays summarization by several turns.
3. **Full summarization** (SummarizationMiddleware): Old messages summarized and offloaded to backend when threshold is reached.
4. **Overflow clip** (SummarizationMiddleware + `_overflow_clip`): Preserved tail further clipped after provider rejection.

Each layer is sufficient for moderate cases. The escalation handles pathological cases (huge tool results + long conversation) without losing recoverability -- content is always persisted to the backend.

### 5.4 Interaction with the Messages Reducer

The `_summarization_event` approach avoids modifying `state["messages"]` directly. This prevents `RemoveMessage(id=REMOVE_ALL_MESSAGES)` from appearing in the checkpoint, avoids conflicts with other middleware, and preserves raw logs for evals. The only time `state["messages"]` is written is when overflow clipping produces replacement ToolMessages. Those carry original `id` values so the reducer overwrites rather than appends.

---

## 6. Configuration Examples

### 6.1 Default Setup

When using `create_deep_agent`, summarization middleware is added automatically with model-aware defaults from `compute_summarization_defaults`.

### 6.2 Custom Thresholds

```python
from deepagents.middleware.summarization import SummarizationMiddleware
from deepagents.backends import FilesystemBackend

summ = SummarizationMiddleware(
    model="gpt-5.4-mini",
    backend=FilesystemBackend(root_dir="/data"),
    trigger=("fraction", 0.85),
    keep=("fraction", 0.10),
)
agent = create_deep_agent(middleware=[summ])
```

### 6.3 With Manual Compaction Tool

```python
from deepagents.middleware.summarization import create_summarization_tool_middleware

agent = create_deep_agent(
    model="openai:gpt-5.4",
    middleware=[create_summarization_tool_middleware("openai:gpt-5.4", StateBackend)],
)
```

### 6.4 Conservative Settings (No Fraction Support)

```python
summ = SummarizationMiddleware(
    model="custom-model",
    backend=backend,
    trigger=("tokens", 170000),
    keep=("messages", 6),
    truncate_args_settings={
        "trigger": ("messages", 20),
        "keep": ("messages", 20),
    },
)
```

---

## 7. Key Source References

| File | Key Exports |
|------|-------------|
| `middleware/summarization.py` | `SummarizationMiddleware`, `SummarizationToolMiddleware`, `create_summarization_middleware`, `create_summarization_tool_middleware`, `compute_summarization_defaults` |
| `middleware/_message_eviction.py` | `_offload_tool_message_content`, `_aoffload_tool_message_content`, `_create_content_preview`, `_extract_text_from_message`, `_build_evicted_content` |
| `middleware/_overflow_clip.py` | `_clip_overflow_tail`, `_aclip_overflow_tail`, `_derive_overflow_clip_threshold_tokens`, `_find_tail_tool_message_batch`, `_slice_read_file_tm` |
| `middleware/_state.py` | `private_state_field_names` (identifies `_summarization_event` as private) |
| `middleware/_utils.py` | `append_to_system_message` (used by `SummarizationToolMiddleware`) |
