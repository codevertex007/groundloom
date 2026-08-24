# Doc 12: FilesystemMiddleware -- Exhaustive Implementation Reference

## Table of Contents

1. [Overview](#1-overview)
2. [The 8 Filesystem Tools](#2-the-8-filesystem-tools)
3. [Tool Schema Definitions](#3-tool-schema-definitions)
4. [Permission Enforcement](#4-permission-enforcement)
5. [_fs_interrupt.py -- Human-in-the-Loop Bridge](#5-_fs_interruptpy----human-in-the-loop-bridge)
6. [Large Tool Result Eviction](#6-large-tool-result-eviction)
7. [_message_eviction.py -- Shared Eviction Primitives](#7-_message_evictionpy----shared-eviction-primitives)
8. [HumanMessage Eviction](#8-humanmessage-eviction)
9. [_overflow_clip.py -- Context Overflow Fallback](#9-_overflow_clippy----context-overflow-fallback)
10. [FilesystemState](#10-filesystemstate)
11. [FilesystemMiddleware Constructor](#11-filesystemmiddleware-constructor)
12. [wrap_model_call Details](#12-wrap_model_call-details)
13. [wrap_tool_call Details](#13-wrap_tool_call-details)
14. [System Prompt Construction](#14-system-prompt-construction)
15. [Subagent Permission Inheritance](#15-subagent-permission-inheritance)
16. [Security Guarantees and Limitations](#16-security-guarantees-and-limitations)
17. [Constants Reference](#17-constants-reference)
18. [Knowledge Verification Questions](#18-knowledge-verification-questions)

---

## 1. Overview

`FilesystemMiddleware` is the largest middleware in the Deep Agents codebase at approximately 2,377 lines
in a single source file. It is a **REQUIRED** middleware -- `create_deep_agent` raises `ValueError` if it
is excluded from the middleware stack.

**Source file:** `libs/deepagents/deepagents/middleware/filesystem.py`

**Supporting modules:**

| File | Lines | Purpose |
|------|-------|---------|
| `filesystem.py` | ~2,377 | Main middleware: 8 tools (incl. `delete`), permissions, eviction |
| `_fs_interrupt.py` | ~182 | Bridges permissions to HumanInTheLoopMiddleware |
| `_message_eviction.py` | ~162 | Shared eviction primitives (offload, preview, templates) |
| `_overflow_clip.py` | ~206 | Context overflow clipping for SummarizationMiddleware |

**Responsibilities:**

1. Provides 8 filesystem tools (ls, read_file, write_file, edit_file, glob, grep, delete, execute)
2. Enforces permission rules via `FilesystemPermission` dataclass
3. Handles large tool result eviction (offload to backend filesystem)
4. Handles large HumanMessage eviction
5. Injects filesystem-specific system prompts into model calls
6. Manages `FilesystemState` with delta-based checkpoint storage
7. Conditionally exposes the `execute` tool based on backend capabilities

**Inheritance:**

```
AgentMiddleware[FilesystemState, ContextT, ResponseT]
    ^
    |
FilesystemMiddleware
```

The middleware sets `state_schema = FilesystemState` as a class attribute, which the agent
framework merges into the overall graph state.

---

## 2. The 8 Filesystem Tools

Each tool is created by a private factory method called from the constructor. All tools are
instances of `StructuredTool` from LangChain.

### Tool Summary Table

| # | Tool Name | Factory Method | Schema | Operation | Eviction Exempt |
|---|-----------|---------------|--------|-----------|-----------------|
| 1 | `ls` | `_create_ls_tool()` | `LsSchema` | read | Yes |
| 2 | `read_file` | `_create_read_file_tool()` | `ReadFileSchema` (video: `ReadVideoFileSchema`) | read | Yes |
| 3 | `write_file` | `_create_write_file_tool()` | `WriteFileSchema` | write | Yes |
| 4 | `edit_file` | `_create_edit_file_tool()` | `EditFileSchema` | write | Yes |
| 5 | `glob` | `_create_glob_tool()` | `GlobSchema` | read | Yes |
| 6 | `grep` | `_create_grep_tool()` | `GrepSchema` | read | Yes |
| 7 | `delete` | `_create_delete_tool()` | `DeleteSchema` | write | Yes |
| 8 | `execute` | `_create_execute_tool()` | `ExecuteSchema` | execute | **No** |

The `execute` tool is the only tool whose results are subject to large-result eviction.

> The `read_file` tool is video-aware: when reading a video file it uses
> `ReadVideoFileSchema` and extracts frames via `middleware/_video.py`
> (`extract_video_frames`, gated by `video_dependencies_available`).

### Tool 1: ls

- **Purpose:** List directory contents.
- **Input:** `path` (str) -- directory to list.
- **Operation:** `"read"` for permission checking.
- **Backend call:** `backend.ls(path)` / `backend.als(path)`.
- **Post-processing:** Results filtered through `_apply_permissions_to_ls_results` if permissions
  are configured, removing entries the agent is not allowed to see.

### Tool 2: read_file

- **Purpose:** Read file contents with optional pagination.
- **Input:** `file_path` (str), `offset` (int, default 0), `limit` (int, default 100).
- **Operation:** `"read"` for permission checking.
- **Backend call:** `backend.read(file_path, offset=offset, limit=limit)`.
- **Post-processing:**
  - Content formatted with line numbers via `format_content_with_line_numbers`.
  - Line number width is `LINE_NUMBER_WIDTH = 6`.
  - Empty files return `EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"`.
  - Oversized results truncated with `READ_FILE_TRUNCATION_MSG` appended.
- **Multimodal support:** Binary files (images, audio, PDFs) are returned as multimodal
  content blocks with appropriate MIME types, detected via `mimetypes.guess_type`.

### Tool 3: write_file

- **Purpose:** Create or overwrite a file.
- **Input:** `file_path` (str), `content` (str).
- **Operation:** `"write"` for permission checking.
- **Backend call:** `backend.write(file_path, content)`.
- **State update:** Written content is stored in `FilesystemState.files` for checkpoint tracking.

### Tool 4: edit_file

- **Purpose:** Edit an existing file using exact string search and replace.
- **Input:** `file_path` (str), `old_string` (str), `new_string` (str), `replace_all` (bool, default False).
- **Operation:** `"write"` for permission checking.
- **Backend call:** `backend.edit(file_path, old_string, new_string, replace_all=replace_all)`.
- **Return type:** `EditResult` containing the diff or error message.

### Tool 5: glob

- **Purpose:** Find files matching a glob pattern.
- **Input:** `pattern` (str), `path` (str | None, optional root directory).
- **Operation:** `"read"` for permission checking.
- **Backend call:** `backend.glob(pattern, path=path)` / `backend.aglob(...)`.
- **Concurrency controls (sync path):**
  - Uses `ThreadPoolExecutor` with `_SYNC_GLOB_WORKERS = 4` workers.
  - A `BoundedSemaphore` limits concurrent in-flight glob operations to 4.
  - `concurrent.futures.wait(timeout=GLOB_TIMEOUT)` enforces a 10-second timeout.
- **Concurrency controls (async path):**
  - Uses `asyncio.wait(timeout=GLOB_TIMEOUT)` with the same 10-second timeout.
- **Timeout behavior:** If the glob exceeds 10 seconds, the result is discarded via
  `_discard_task_result` and a timeout message is returned to the agent.
- **Post-processing:** Results filtered through `_apply_permissions_to_glob_results`.

### Tool 6: grep

- **Purpose:** Search file contents by regex pattern.
- **Input:** `pattern` (str), `path` (str | None), `glob` (str | None, file filter),
  `output_mode` ("files_with_matches" | "content" | "count", default "files_with_matches").
- **Operation:** `"read"` for permission checking.
- **Backend call:** `backend.grep(pattern, path=path, glob=glob_filter)`.
- **Post-processing:**
  - Grep matches filtered through `_filter_grep_matches_by_permission`.
  - Output formatted by `_format_grep_tool_result` according to `output_mode`.

### Tool 7: execute

- **Purpose:** Run shell commands in the backend sandbox.
- **Input:** `command` (str), `timeout` (int | None).
- **Operation:** `"execute"` for permission checking.
- **Availability gate:** Only available if `supports_execution(backend)` returns True.
  The helper checks whether the backend implements `SandboxBackendProtocol`.
- **Backend call:** `backend.execute(command, timeout=timeout)`.
- **Timeout validation:**
  - `timeout >= 0` required.
  - `timeout <= max_execute_timeout` (constructor parameter, default 3600 seconds).
  - `execute_accepts_timeout(backend)` checked to determine if timeout param is supported.
- **Eviction:** This is the only tool NOT in `TOOLS_EXCLUDED_FROM_EVICTION`. Large execution
  outputs are offloaded to the backend filesystem.

### supports_execution Helper

```python
def supports_execution(backend: BackendProtocol) -> bool:
    if isinstance(backend, CompositeBackend):
        return isinstance(backend.default, SandboxBackendProtocol)
    return isinstance(backend, SandboxBackendProtocol)
```

For `CompositeBackend`, the check examines the `.default` sub-backend. For all other
backends, it checks the backend instance directly.

---

## 3. Tool Schema Definitions

All schemas are Pydantic `BaseModel` subclasses defined in `filesystem.py`.

```python
class LsSchema(BaseModel):
    path: str

class ReadFileSchema(BaseModel):
    file_path: str
    offset: int = DEFAULT_READ_OFFSET      # 0
    limit: int = DEFAULT_READ_LIMIT         # 100

class WriteFileSchema(BaseModel):
    file_path: str
    content: str

class EditFileSchema(BaseModel):
    file_path: str
    old_string: str
    new_string: str
    replace_all: bool = False

class GlobSchema(BaseModel):
    pattern: str
    path: str | None = None

class GrepSchema(BaseModel):
    pattern: str
    path: str | None = None
    glob: str | None = None
    output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches"

class ExecuteSchema(BaseModel):
    command: str
    timeout: int | None = None
```

Note the field naming inconsistency: `LsSchema` uses `path` while `ReadFileSchema`, `WriteFileSchema`,
and `EditFileSchema` use `file_path`. This matters for `_FS_TOOL_PATH_ARGS` mapping in `_fs_interrupt.py`.

---

## 4. Permission Enforcement

### 4.1 FilesystemPermission Dataclass

```python
@dataclass
class FilesystemPermission:
    operations: list[FilesystemOperation]   # list of "read" | "write"
    paths: list[str]                        # glob patterns
    mode: Literal["allow", "deny", "interrupt"] = "allow"
```

**`FilesystemOperation`** is defined as:

```python
FilesystemOperation = Literal["read", "write"]
```

### 4.2 Path Validation in `__post_init__`

The `__post_init__` method validates every path in the `paths` list:

1. **Must start with `/`** -- relative paths are rejected.
2. **No `..` segments allowed** -- prevents directory traversal attacks.
3. **No `~` characters allowed** -- prevents home directory expansion.

Violations raise `ValueError` with a descriptive message.

### 4.3 Default Tool-to-Operation Mapping

```python
_DEFAULT_FS_TOOL_OPS: dict[str, FilesystemOperation] = {
    "ls": "read",
    "read_file": "read",
    "glob": "read",
    "grep": "read",
    "write_file": "write",
    "edit_file": "write",
}
```

The `execute` tool maps to the `"execute"` operation but is handled separately since
`FilesystemOperation` only covers `"read"` and `"write"`.

### 4.4 `_check_fs_permission` Function

```python
def _check_fs_permission(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path: str,
) -> Literal["allow", "deny", "interrupt"]
```

**Algorithm -- First-match-wins evaluation:**

1. Iterate through `rules` in order.
2. For each rule, check if the `operation` is in `rule.operations`.
3. If yes, check if `path` matches any pattern in `rule.paths` using
   `wcmatch.glob.globmatch` with `_FS_WCMATCH_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR`.
4. If a match is found, return `rule.mode` immediately.
5. If no rule matches after exhausting all rules, return `"allow"` (default-allow policy).

**Critical implication:** The default-allow policy means that any path/operation combination
not explicitly covered by a rule is permitted. Explicit deny rules must be placed at the top
of the rules list to take priority.

### 4.5 Permission Filtering Functions

Several helper functions apply permissions to tool results as defense-in-depth:

```python
def _filter_paths_by_permission(rules, operation, paths) -> list[str]
def _filter_file_infos_by_permission(rules, infos, *, operation) -> list[FileInfo]
def _filter_grep_matches_by_permission(rules, matches, *, operation) -> list[GrepMatch]
def _apply_permissions_to_ls_results(rules, entries) -> list[str]
def _apply_permissions_to_glob_results(rules, matches) -> list[str]
```

These functions post-filter tool results, removing entries that the agent is not
permitted to see. The primary check happens before the tool executes, but results
are also filtered afterward for tools that return multiple paths (ls, glob, grep).
Only `deny`-mode paths are filtered out; `interrupt`-mode paths pass through because
the HITL approval has already happened by the time result-filtering runs.

### 4.6 Permission Enforcement Flow Diagram

```
Agent calls filesystem tool (e.g., read_file with path="/etc/secrets")
    |
    v
wrap_tool_call / awrap_tool_call
    |
    v
Extract path argument from tool call args
    |
    v
_check_fs_permission(rules, operation, path)
    |
    +---> "allow"  --> Execute tool normally
    |                      |
    |                      v
    |                  Post-filter results (for multi-path tools)
    |                      |
    |                      v
    |                  Return result to agent
    |
    +---> "deny"   --> Return permission-denied error message
    |                  (tool does NOT execute)
    |
    +---> "interrupt" --> Delegate to HumanInTheLoopMiddleware
                          via _fs_interrupt.py
                          (human decides: approve/edit/reject/respond)
```

---

## 5. _fs_interrupt.py -- Human-in-the-Loop Bridge

**Source:** `libs/deepagents/deepagents/middleware/_fs_interrupt.py` (~182 lines)

This module bridges `FilesystemPermission` rules with `HumanInTheLoopMiddleware`. When a
permission rule has `mode="interrupt"`, the filesystem tool call is paused and presented
to a human for approval.

### 5.1 ToolScope Type

```python
ToolScope = Literal["exact", "bulk"]
```

- **`"exact"`** -- Tools with a single, explicit path argument: `read_file`, `write_file`, `edit_file`.
- **`"bulk"`** -- Tools with pattern-based or directory arguments: `ls`, `glob`, `grep`.

### 5.2 _FS_TOOL_PATH_ARGS Mapping

Maps each tool name to a tuple of `(operation, path_arg_name, scope, pattern_arg_name)`:

```python
_FS_TOOL_PATH_ARGS: dict[str, tuple[FilesystemOperation, str, ToolScope, str | None]] = {
    "ls":         ("read",  "path",      "bulk",  None),
    "read_file":  ("read",  "file_path", "exact", None),
    "write_file": ("write", "file_path", "exact", None),
    "edit_file":  ("write", "file_path", "exact", None),
    "glob":       ("read",  "path",      "bulk",  "pattern"),
    "grep":       ("read",  "path",      "bulk",  None),
}
```

Note: The `execute` tool is not in this mapping because it is handled through a different
code path for interrupt evaluation (the `"execute"` operation falls outside `FilesystemOperation`).

### 5.3 Predicate Factory Functions

These functions create `Callable[[ToolCallRequest], bool]` predicates that determine
whether an interrupt should fire for a given tool call.

#### `_make_fs_when_predicate`

```python
def _make_fs_when_predicate(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path_arg_name: str,
    scope: ToolScope,
    pattern_arg_name: str | None = None,
) -> Callable[[ToolCallRequest], bool]
```

Dispatcher that delegates to `_make_exact_when_predicate` or `_make_bulk_when_predicate`
based on `scope`.

#### `_make_exact_when_predicate`

```python
def _make_exact_when_predicate(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path_arg_name: str,
) -> Callable[[ToolCallRequest], bool]
```

For exact-scope tools. The returned predicate:
1. Extracts the path from `tool_call.args[path_arg_name]`.
2. Normalizes the path.
3. Calls `_check_fs_permission(rules, operation, normalized_path)`.
4. Returns `True` (fire interrupt) if result is `"interrupt"`.

#### `_make_bulk_when_predicate`

```python
def _make_bulk_when_predicate(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path_arg_name: str,
    pattern_arg_name: str | None = None,
) -> Callable[[ToolCallRequest], bool]
```

For bulk-scope tools. The returned predicate:
1. Precomputes `interrupt_anchors` -- a list of `_glob_anchor(pattern)` values from all
   interrupt-mode rules whose operations include the given operation.
2. Extracts the search path from `tool_call.args[path_arg_name]`.
3. If path is `None` (not provided), fires unconditionally (the search could reach anywhere).
4. Normalizes `"/."` to `"/"`.
5. Checks if any anchor overlaps with the normalized path via `_paths_overlap`.
6. If a `pattern_arg_name` is given (for `glob`), also checks `_bulk_pattern_fires`.

### 5.4 `_bulk_pattern_fires`

```python
def _bulk_pattern_fires(raw_pattern: str, interrupt_anchors: list[str]) -> bool
```

Catches cases where the glob tool's `pattern` argument could reach interrupt-protected
subtrees even if the `path` argument appears safe:

1. If the pattern is an absolute path (starts with `/`), checks overlap with each anchor.
2. If the pattern contains `..` (directory traversal), fires unconditionally.

### 5.5 `_build_interrupt_on_from_permissions`

```python
def _build_interrupt_on_from_permissions(
    rules: list[FilesystemPermission],
) -> dict[str, InterruptOnConfig]
```

Entry point that converts permission rules into `InterruptOnConfig` dictionaries:

1. Iterates over `_FS_TOOL_PATH_ARGS`.
2. For each tool, checks if any rule has `mode="interrupt"` for the tool's operation.
3. If yes, creates an `InterruptOnConfig` with:
   - `when`: predicate from `_make_fs_when_predicate`
   - `allowed_decisions`: `["approve", "edit", "reject", "respond"]`
4. Returns a dict mapping tool names to their interrupt configs.

These configs are merged with user-supplied `interrupt_on` in `create_deep_agent` via
`_merge_fs_interrupt_on()`, where user-supplied entries override generated ones per tool name.

---

## 6. Large Tool Result Eviction

### 6.1 Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `tool_token_limit_before_evict` | `20000` tokens | Threshold for evicting tool results |
| `NUM_CHARS_PER_TOKEN` | `4` | Character-to-token estimation ratio |

Effective character threshold: `20000 * 4 = 80,000 characters`.

### 6.2 TOOLS_EXCLUDED_FROM_EVICTION

```python
TOOLS_EXCLUDED_FROM_EVICTION = ("ls", "glob", "grep", "read_file", "edit_file", "write_file")
```

This is a **tuple** (not a set). All 6 read/write tools are exempt. Only `execute` results
are subject to eviction.

The rationale for each exclusion:
- `ls`, `glob`, `grep` -- have built-in truncation within the tool itself
- `read_file` -- truncation would cause problematic behavior with long lines
- `edit_file`, `write_file` -- return minimal confirmation messages, never large

### 6.3 Eviction Flow

The eviction logic lives in `wrap_tool_call` / `awrap_tool_call` and delegates to
`_intercept_large_tool_result` / `_aintercept_large_tool_result`, which in turn calls
`_process_large_message` / `_aprocess_large_message`.

```
wrap_tool_call / awrap_tool_call
    |
    v
Call inner handler -> get ToolMessage result
    |
    v
Is tool name in TOOLS_EXCLUDED_FROM_EVICTION?
    |
    +---> Yes --> Return result unchanged
    |
    +---> No  --> _intercept_large_tool_result
                      |
                      v
                  _process_large_message
                      |
                      v
                  Extract text content via _extract_text_from_message
                      |
                      v
                  len(text) > NUM_CHARS_PER_TOKEN * tool_token_limit_before_evict ?
                      |
                      +---> No  --> Return (original_message, False)
                      |
                      +---> Yes --> Offload content to backend:
                                    path = {large_tool_results_prefix}/{sanitized_tool_call_id}
                                        |
                                        v
                                    _create_content_preview(text, head_lines=5, tail_lines=5)
                                        |
                                        v
                                    Format TOO_LARGE_TOOL_MSG template
                                        |
                                        v
                                    _build_evicted_tool_message with replacement content
                                        |
                                        v
                                    Return (evicted_message, True)
```

### 6.4 Offload Path

Large tool results are written to:

```
{large_tool_results_prefix}/{sanitized_tool_call_id}
```

Where `large_tool_results_prefix` is derived from the backend's `artifacts_root` during
middleware construction (typically `/large_tool_results`).

The `sanitize_tool_call_id` function (from `deepagents.backends.utils`) ensures the
tool call ID is safe for use as a filesystem path component.

### 6.5 Command Handling

`_intercept_large_tool_result` handles both plain `ToolMessage` and `Command`-wrapped
results. If the result is a `Command`, the method extracts the `ToolMessage`, processes
it through `_process_large_message`, and re-wraps if needed.

---

## 7. _message_eviction.py -- Shared Eviction Primitives

**Source:** `libs/deepagents/deepagents/middleware/_message_eviction.py` (~162 lines)

This module provides the low-level building blocks used by both tool result eviction
(in `filesystem.py`) and context overflow clipping (in `_overflow_clip.py`).

### 7.1 TOO_LARGE_TOOL_MSG Template

```python
TOO_LARGE_TOOL_MSG = """Tool result too large, the result of this tool call \
{tool_call_id} was saved in the filesystem at this path: {file_path}

You can read the result from the filesystem by using the read_file tool, \
but make sure to only read part of the result at a time.

You can do this by specifying an offset and limit in the read_file tool call. \
For example, to read the first 100 lines, you can use the read_file tool \
with offset=0 and limit=100.

Here is a preview showing the head and tail of the result (lines of the form \
`... [N lines truncated] ...` indicate omitted lines in the middle of the content):

{content_sample}
"""
```

**Placeholders:**
- `{tool_call_id}` -- the original tool call ID
- `{file_path}` -- path where full content was offloaded
- `{content_sample}` -- head+tail preview from `_create_content_preview`

### 7.2 `_create_content_preview`

```python
def _create_content_preview(
    content_str: str,
    *,
    head_lines: int = 5,
    tail_lines: int = 5,
) -> str
```

Creates a head+tail preview of large content:

1. Split content into lines.
2. If total lines <= `head_lines + tail_lines` (default 5 + 5 = 10): return all lines
   (each truncated to 1000 chars), formatted with line numbers.
3. Otherwise: take first `head_lines` lines, append `"\n... [N lines truncated] ...\n"`
   (where N is the count of omitted lines), then append the last `tail_lines` lines. All
   lines are formatted with line numbers via `format_content_with_line_numbers`.

The truncation marker shows the exact number of omitted lines, e.g.,
`"... [2847 lines truncated] ..."`.

### 7.3 `_extract_text_from_message`

```python
def _extract_text_from_message(message: BaseMessage) -> str
```

Extracts all text content from a message, joining text blocks:

- Iterates over `message.content_blocks`.
- Collects blocks where `block["type"] == "text"`.
- Joins their `block["text"]` values.
- Ignores non-text blocks (images, audio, etc.).

### 7.4 `_build_evicted_content`

```python
def _build_evicted_content(
    message: ToolMessage,
    replacement_text: str,
) -> str | list[ContentBlock]
```

Builds the replacement content for an evicted message:

- **String content:** Returns `replacement_text` directly.
- **List content (multimodal):** Keeps all non-text blocks (images, audio), prepends a
  single text block containing `replacement_text`. This preserves any media attachments
  while replacing the text.

### 7.5 `_build_evicted_tool_message`

```python
def _build_evicted_tool_message(
    message: ToolMessage,
    evicted_content: str | list[ContentBlock],
) -> ToolMessage
```

Creates a new `ToolMessage` with evicted content, preserving all metadata:
- `tool_call_id`
- `name`
- `id`
- `artifact`
- `status`
- `additional_kwargs`
- `response_metadata`

### 7.6 Offload Functions

```python
def _offload_tool_message_content(
    message: ToolMessage,
    content_str: str,
    backend: BackendProtocol,
    large_tool_results_prefix: str,
) -> ToolMessage | None

async def _aoffload_tool_message_content(
    message: ToolMessage,
    content_str: str,
    backend: BackendProtocol,
    large_tool_results_prefix: str,
) -> ToolMessage | None
```

Write the full content to `{large_tool_results_prefix}/{sanitized_tool_call_id}` via
`backend.write` / `backend.awrite`. On success, return a `ToolMessage` with evicted
content (using `_build_evicted_content` and `_build_evicted_tool_message`). On failure
(write error), return `None` and the original message is kept unchanged.

---

## 8. HumanMessage Eviction

### 8.1 Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `human_message_token_limit_before_evict` | `50000` tokens | Threshold for evicting HumanMessages |
| `NUM_CHARS_PER_TOKEN` | `4` | Character-to-token estimation ratio |

Effective character threshold: `50000 * 4 = 200,000 characters`.

This threshold is 2.5x higher than the tool result threshold (20,000 tokens), reflecting
that HumanMessages are typically more important to preserve in context.

### 8.2 TOO_LARGE_HUMAN_MSG Template

```python
TOO_LARGE_HUMAN_MSG = """Message content too large and was saved to the \
filesystem at: {file_path}

You can read the full content using the read_file tool with pagination \
(offset and limit parameters).

Here is a preview showing the head and tail of the content:

{content_sample}
"""
```

**Placeholders:**
- `{file_path}` -- path where full content was offloaded
- `{content_sample}` -- head+tail preview

### 8.3 Eviction Flow

HumanMessage eviction occurs in `wrap_model_call` / `awrap_model_call`, before the model
is invoked. The flow is handled by `_evict_and_truncate_messages` /
`_aevict_and_truncate_messages`.

```
wrap_model_call / awrap_model_call
    |
    v
_evict_and_truncate_messages
    |
    v
Scan all messages for large HumanMessages
    |
    v
For each HumanMessage:
    len(_extract_text_from_message(msg)) > NUM_CHARS_PER_TOKEN * human_message_token_limit ?
        |
        +---> No  --> Skip
        |
        +---> Yes --> Offload to {conversation_history_prefix}/{uuid}.md
                          |
                          v
                      _build_truncated_human_message(message, file_path)
                          |
                          v
                      Tag message with lc_evicted_to in additional_kwargs
                          |
                          v
                      Atomically replace in state via Overwrite (for DeltaChannel)
```

### 8.4 Key Differences from Tool Result Eviction

| Aspect | Tool Result Eviction | HumanMessage Eviction |
|--------|---------------------|-----------------------|
| Token threshold | 20,000 | 50,000 |
| Trigger point | `wrap_tool_call` (after tool runs) | `wrap_model_call` (before model runs) |
| Target message type | `ToolMessage` | `HumanMessage` |
| Offload path | `{large_tool_results_prefix}/{tool_call_id}` | `{conversation_history_prefix}/{uuid}.md` |
| State update | Direct message replacement | Atomic `Overwrite` for `DeltaChannel` |
| Exempt tools | 6 of 7 (all except execute) | N/A |
| Already-evicted check | By tool name exclusion list | `lc_evicted_to` flag in `additional_kwargs` |

### 8.5 Helper Functions

```python
def _build_evicted_human_content(
    message: HumanMessage,
    replacement_text: str,
) -> str | list[ContentBlock]
```

Analogous to `_build_evicted_content` for `ToolMessage`, but for `HumanMessage`:
preserves non-text content blocks while replacing text.

```python
def _build_truncated_human_message(
    message: HumanMessage,
    file_path: str,
) -> HumanMessage
```

Creates a replacement `HumanMessage` with the `TOO_LARGE_HUMAN_MSG` template filled in,
and sets `additional_kwargs["lc_evicted_to"] = file_path` to prevent re-eviction on
subsequent model calls.

### 8.6 State Update Mechanics

The `_evict_and_truncate_messages` method returns a `tuple[list[AnyMessage], Command | None]`:

- The `list[AnyMessage]` contains the modified message list with evicted HumanMessages replaced.
- The `Command` (if present) uses `Overwrite` to atomically update the messages in the
  `DeltaChannel`-backed state. This is necessary because `DeltaChannel` requires explicit
  overwrite semantics rather than in-place mutation.

Static helpers `_unwrap_command_messages` and `_rewrap_command_messages` handle the
conversion between `Command`-wrapped and plain message lists.

---

## 9. _overflow_clip.py -- Context Overflow Fallback

**Source:** `libs/deepagents/deepagents/middleware/_overflow_clip.py` (~206 lines)

This module is used by `SummarizationMiddleware` as a fallback when `ContextOverflowError`
occurs. While not directly part of `FilesystemMiddleware`, it closely depends on the filesystem
eviction primitives and shares the same backend offload mechanism.

### 9.1 Entry Points

```python
def _clip_overflow_tail(
    preserved_messages: list[AnyMessage],
    backend: BackendProtocol,
    *,
    keep: ContextSize,
    max_input_tokens: int | None,
    token_counter: TokenCounter,
    large_tool_results_prefix: str,
) -> tuple[list[AnyMessage], list[AnyMessage]]

async def _aclip_overflow_tail(
    preserved_messages: list[AnyMessage],
    backend: BackendProtocol,
    *,
    keep: ContextSize,
    max_input_tokens: int | None,
    token_counter: TokenCounter,
    large_tool_results_prefix: str,
) -> tuple[list[AnyMessage], list[AnyMessage]]
```

**Returns:** `(modified_preserved_messages, replacement_tool_messages_for_state)`

The replacement tool messages have their `id` set (via `uuid.uuid4()` if `None`) so that
the `add_messages` reducer can overwrite the originals by matching on message ID.

### 9.2 Threshold Derivation

```python
def _derive_overflow_clip_threshold_tokens(
    keep: ContextSize,
    max_input_tokens: int | None,
) -> int
```

Derives the token threshold that determines whether clipping engages:

- If `keep.kind == "tokens"`: returns `int(keep.value)`.
- If `keep.kind == "fraction"` and `max_input_tokens` is not None:
  returns `int(max_input_tokens * keep.value)`.
- Fallback: `5_000` tokens.

Clipping only engages if the tail `ToolMessage` batch's token count meets or exceeds
this threshold.

### 9.3 Tail Batch Detection

```python
def _find_tail_tool_message_batch(
    messages: list[AnyMessage],
) -> tuple[int, list[ToolMessage]] | None
```

Finds the trailing batch of consecutive `ToolMessage`s at the end of the message list.
Returns `(start_index, batch)` or `None` if the messages don't end with `ToolMessage`s.

### 9.4 Two Clipping Strategies

Each `ToolMessage` in the tail batch is clipped using one of two strategies:

#### Strategy 1: read_file Results (Head Slice)

```python
def _slice_read_file_tm(msg: ToolMessage, original_path: str) -> ToolMessage
```

For `read_file` tool results:
1. Slices content to the first **4,000 characters**.
2. Appends a truncation notice pointing back to the original `file_path`.
3. No backend write needed -- the file already exists at the original path.

The original path is recovered via:

```python
def _read_file_original_path(
    msg: ToolMessage,
    tc_index: dict[str, dict[str, Any]],
) -> str | None
```

Which looks up the `file_path` argument from the matching tool call in the `AIMessage`.

#### Strategy 2: All Other Tools (Full Offload)

For non-`read_file` results:
1. Full content offloaded via `_offload_tool_message_content` to
   `/large_tool_results/{tool_call_id}`.
2. Content replaced with `TOO_LARGE_TOOL_MSG` template.

### 9.5 Tool Call Index

```python
def _build_tool_call_index(
    messages: list[AnyMessage],
) -> dict[str, dict[str, Any]]
```

Builds a mapping from `tool_call_id` to tool call dict by scanning all `AIMessage.tool_calls`
in the message list. Used by `_read_file_original_path` to recover the original arguments.

### 9.6 Async Concurrency

The async variant `_aclip_overflow_tail` uses `asyncio.gather` for concurrent offloading
of multiple tool messages in the tail batch, improving latency when several large results
need to be offloaded simultaneously.

### 9.7 Per-Message Clipping Helpers

```python
def _clip_one_tail_message(msg, tc_index, backend, large_tool_results_prefix) -> ToolMessage | None
async def _aclip_one_tail_message(msg, tc_index, backend, large_tool_results_prefix) -> ToolMessage | None
```

Process a single `ToolMessage` from the tail batch. Returns a replacement `ToolMessage`
if clipping was applied, or `None` if the message was left unchanged (e.g., already small
enough or offload failed).

---

## 10. FilesystemState

```python
class FilesystemState(AgentState):
    files: Annotated[
        NotRequired[dict[str, FileData]],
        DeltaChannel(_file_data_delta_reducer, snapshot_frequency=50),
    ]
```

### 10.1 DeltaChannel Configuration

- **Reducer:** `_file_data_delta_reducer`
- **Snapshot frequency:** `50` -- a full snapshot of the `files` dict is serialized every
  50 deltas (intermediate updates store only the changed key-value pairs).

### 10.2 Delta Reducer

```python
def _file_data_delta_reducer(
    left: dict[str, FileData] | None,
    values: list[dict[str, FileData | None]],
) -> dict[str, FileData]:
```

Merges a list of delta dicts into the existing state:
- Each delta dict maps file paths to `FileData` values.
- A `None` value for a path means deletion (the key is removed from the state).
- Non-None values are upserted.
- Uses a single dict copy + one pass over all writes for efficiency.

### 10.3 File Data Reducer (Legacy)

```python
def _file_data_reducer(left: dict, right: dict) -> dict[str, FileData]
```

The non-delta reducer that merges two file state dicts. Supports `None` for deletion.
Used as a fallback or in non-delta contexts.

### 10.4 State Tracking Purpose

`FilesystemState.files` tracks the contents of files written or edited by the agent.
This enables:
- Checkpoint persistence via `StateBackend`
- Efficient delta-based storage (only changed files are serialized between snapshots)
- State recovery on agent restart

---

## 11. FilesystemMiddleware Constructor

```python
class FilesystemMiddleware(AgentMiddleware[FilesystemState, ContextT, ResponseT]):
    state_schema = FilesystemState

    def __init__(
        self,
        *,
        backend: BACKEND_TYPES | None = None,
        system_prompt: str | None = None,
        custom_tool_descriptions: Mapping[str, str] | None = None,
        tool_token_limit_before_evict: int | None = 20000,
        human_message_token_limit_before_evict: int | None = 50000,
        max_execute_timeout: int = 3600,
        _permissions: list[FilesystemPermission] | None = None,
    ) -> None:
```

### 11.1 Parameter Details

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | `BACKEND_TYPES \| None` | `None` | Backend instance or factory |
| `system_prompt` | `str \| None` | `None` | Custom system prompt override |
| `custom_tool_descriptions` | `Mapping[str, str] \| None` | `None` | Per-tool description overrides |
| `tool_token_limit_before_evict` | `int \| None` | `20000` | Token threshold for tool result eviction |
| `human_message_token_limit_before_evict` | `int \| None` | `50000` | Token threshold for HumanMessage eviction |
| `max_execute_timeout` | `int` | `3600` | Maximum allowed timeout for execute tool (seconds) |
| `_permissions` | `list[FilesystemPermission] \| None` | `None` | Permission rules (underscore = internal API) |

### 11.2 Instance Attributes Set in Constructor

| Attribute | Source | Description |
|-----------|--------|-------------|
| `self.backend` | `backend` param | Resolved backend instance |
| `self._large_tool_results_prefix` | Derived from `artifacts_root` | Path prefix for offloaded tool results |
| `self._conversation_history_prefix` | Derived from `artifacts_root` | Path prefix for evicted HumanMessages |
| `self._dynamic_system_prompt_cache` | `dict[bool, str]` | Cached system prompts (keyed by `include_execution`) |
| `self._custom_system_prompt` | `system_prompt` param | Custom system prompt override |
| `self._custom_tool_descriptions` | `custom_tool_descriptions` param | Per-tool description overrides |
| `self._tool_token_limit_before_evict` | `tool_token_limit_before_evict` param | Token eviction threshold |
| `self._human_message_token_limit_before_evict` | `human_message_token_limit_before_evict` param | HumanMessage eviction threshold |
| `self._max_execute_timeout` | `max_execute_timeout` param | Max execute timeout |
| `self._permissions` | `_permissions` param | Permission rules list |
| `self._glob_executor` | `ThreadPoolExecutor(max_workers=4)` | Thread pool for sync glob |
| `self._glob_slots` | `BoundedSemaphore(4)` | Concurrency limiter for sync glob |
| `self.tools` | List of 8 `StructuredTool` | The filesystem tools |

### 11.3 Tool Creation in Constructor

The constructor creates all 8 tools by calling the private factory methods:

```python
self.tools = [
    self._create_ls_tool(),
    self._create_read_file_tool(),
    self._create_write_file_tool(),
    self._create_edit_file_tool(),
    self._create_glob_tool(),
    self._create_grep_tool(),
    self._create_delete_tool(),
    self._create_execute_tool(),
]
```

Each factory method constructs a `StructuredTool` with:
- Tool name (e.g., `"ls"`, `"read_file"`)
- Description from the corresponding constant (e.g., `LIST_FILES_TOOL_DESCRIPTION`),
  potentially overridden by `custom_tool_descriptions`
- The Pydantic schema for argument validation
- A `func` (sync) and `coroutine` (async) implementation

---

## 12. wrap_model_call Details

The `wrap_model_call` / `awrap_model_call` methods are called before each model invocation.
They modify the `ModelRequest` to inject tools, system prompts, and handle eviction.

### 12.1 Processing Steps

```
wrap_model_call(request, handler)
    |
    v
Step 1: Resolve backend
    |
    v
Step 2: Check if backend supports execution
        supports_execution(backend) -> bool
    |
    v
Step 3: Build dynamic system prompt
        _build_dynamic_system_prompt(include_execution=supports_exec)
        Cached in self._dynamic_system_prompt_cache[supports_exec]
    |
    v
Step 4: Inject system prompts via append_to_system_message()
        a. Filesystem system prompt (tool descriptions, large results prefix)
        b. Execution system prompt (if backend supports execution)
        c. _route_host_path_prompt(backend) -- virtual-to-host path mapping
        d. Custom system prompt (if provided)
    |
    v
Step 5: Filter tools
        If backend does NOT support SandboxBackendProtocol:
            Remove "execute" tool from request.tools
        Result: 7 tools (with execute) or 6 tools (without execute)
    |
    v
Step 6: HumanMessage eviction
        _evict_and_truncate_messages(request)
        Offload oversized HumanMessages, update state via Overwrite
    |
    v
Step 7: Call inner handler with modified request
    |
    v
Return response
```

### 12.2 `_build_dynamic_system_prompt`

```python
def _build_dynamic_system_prompt(self, *, include_execution: bool) -> str
```

Builds and caches the filesystem system prompt. The cache key is `include_execution` (bool),
so at most 2 prompts are cached. This avoids rebuilding the prompt string on every model call.

### 12.3 `_route_host_path_prompt`

```python
def _route_host_path_prompt(backend: BackendProtocol) -> str
```

Module-level function that builds a system prompt fragment describing the mapping between
virtual paths (as seen by the agent) and host paths (on the actual filesystem). This helps
the agent understand path translation when working with `CompositeBackend` configurations
that route different path prefixes to different underlying backends.

### 12.4 Execute Tool Filtering

The execute tool filtering logic in `wrap_model_call`:

```python
has_execute_tool = any(
    (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
    for tool in request.tools
)

backend_supports_execution = False
if has_execute_tool:
    backend = self._get_backend(request.runtime)
    backend_supports_execution = supports_execution(backend)

    if not backend_supports_execution:
        filtered_tools = [
            tool for tool in request.tools
            if (tool.name if hasattr(tool, "name") else tool.get("name")) != "execute"
        ]
        request = request.override(tools=filtered_tools)
        has_execute_tool = False
```

---

## 13. wrap_tool_call Details

The `wrap_tool_call` / `awrap_tool_call` methods are called for each tool invocation.
They handle large result eviction for non-exempt tools.

### 13.1 Processing Steps

```
wrap_tool_call(request, handler)
    |
    v
Step 1: Call inner handler -> get ToolMessage or Command result
    |
    v
Step 2: Is tool name in TOOLS_EXCLUDED_FROM_EVICTION?
    |
    +---> Yes --> Return result unchanged
    |
    +---> No  --> Step 3: _intercept_large_tool_result(result, runtime)
                      |
                      v
                  _process_large_message(message, resolved_backend)
                      |
                      v
                  If eviction occurred:
                      Return evicted ToolMessage (possibly wrapped in Command)
                  Else:
                      Return original ToolMessage
```

### 13.2 `_intercept_large_tool_result`

```python
def _intercept_large_tool_result(
    self,
    tool_result: ToolMessage | Command,
    runtime: ToolRuntime,
) -> ToolMessage | Command
```

Handles both plain `ToolMessage` and `Command`-wrapped results. If the result is a
`Command`, extracts the `ToolMessage`, processes it, and re-wraps if needed.

### 13.3 `_process_large_message`

```python
def _process_large_message(
    self,
    message: ToolMessage,
    resolved_backend: BackendProtocol,
) -> tuple[ToolMessage, bool]
```

Returns `(possibly_evicted_message, was_evicted)`. The `bool` flag lets the caller
know whether the message content was modified.

---

## 14. System Prompt Construction

### 14.1 Filesystem System Prompt Template

The `_FILESYSTEM_SYSTEM_PROMPT_TEMPLATE` is parameterized by `{large_tool_results_prefix}`
and includes:
- Instructions for using filesystem tools
- The requirement that all file paths must start with `/`
- Guidance on using pagination (offset/limit) for large files
- Description of where offloaded large tool results are stored
- Instructions for reading offloaded content with `read_file`

### 14.2 Pre-formatted Prompt

```python
FILESYSTEM_SYSTEM_PROMPT = _FILESYSTEM_SYSTEM_PROMPT_TEMPLATE.format(
    large_tool_results_prefix="/large_tool_results"
)
```

### 14.3 Execution System Prompt

```python
EXECUTION_SYSTEM_PROMPT = """## Execute Tool `execute`

You have access to an `execute` tool for running shell commands in a sandboxed environment.
Use this tool to run commands, scripts, tests, builds, and other shell operations.

- execute: run a shell command in the sandbox (returns output and exit code)"""
```

Appended only when the backend supports `SandboxBackendProtocol`.

### 14.4 Tool Description Constants

Each tool has a description constant used in the tool's `StructuredTool` definition:

| Constant | Tool |
|----------|------|
| `LIST_FILES_TOOL_DESCRIPTION` | ls |
| `READ_FILE_TOOL_DESCRIPTION` | read_file |
| `EDIT_FILE_TOOL_DESCRIPTION` | edit_file |
| `WRITE_FILE_TOOL_DESCRIPTION` | write_file |
| `GLOB_TOOL_DESCRIPTION` | glob |
| `GREP_TOOL_DESCRIPTION` | grep |
| `EXECUTE_TOOL_DESCRIPTION` | execute |

These can be overridden per-tool via the `custom_tool_descriptions` constructor parameter.

---

## 15. Subagent Permission Inheritance

From `graph.py`, subagent permission handling follows this logic:

```python
subagent_permissions = spec.get("permissions", permissions)
```

### 15.1 Rules

1. **Explicit permissions:** If a subagent's spec includes a `"permissions"` key, those
   permissions **replace** the parent's entirely. There is no merging.
2. **Inherited permissions:** If a subagent's spec omits `"permissions"`, it inherits the
   parent agent's permission rules unchanged.
3. **Per-middleware instance:** Each subagent's `FilesystemMiddleware` receives its own
   `_permissions` parameter, so permission evaluation is instance-scoped.

### 15.2 Implications

- A subagent can have **more permissive** rules than its parent (if explicitly configured).
- A subagent can have **more restrictive** rules than its parent.
- There is no automatic intersection or union of parent/child permission sets.
- The responsibility for ensuring subagent permissions are appropriate lies with the
  agent graph designer.

---

## 16. Security Guarantees and Limitations

### 16.1 Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| FilesystemMiddleware cannot be excluded | `create_deep_agent` raises `ValueError` |
| Path traversal blocked in permission patterns | `__post_init__` rejects `..` and `~` |
| First-match-wins with default-allow | Explicit deny rules at top take priority |
| Large results don't overflow context | Automatic eviction to backend filesystem |
| HumanMessages don't overflow context | Automatic eviction before model call |
| Execute tool gated on backend capability | `supports_execution` check |
| Execute timeout bounded | `max_execute_timeout` enforced (default 3600s) |
| Post-hoc result filtering | `ls`, `glob`, `grep` results filtered after execution |

### 16.2 Limitations

| Limitation | Description |
|------------|-------------|
| Tool-level enforcement only | Permissions are checked at the middleware tool layer, NOT at the backend level. Direct `backend.read(path)` calls bypass all permission checks. |
| Default-allow policy | If no rule matches a path/operation, the call is ALLOWED. Incomplete rule sets silently permit access. |
| No backend-level sandboxing | The backend itself does not enforce filesystem permissions; the middleware is the sole enforcement point. |
| No path normalization in rules | Permission patterns use raw glob matching; symlinks or mount-point tricks could potentially bypass rules. |
| Character-based token estimation | `NUM_CHARS_PER_TOKEN = 4` is a rough heuristic that may over- or under-estimate actual token counts. |
| Execute bypasses file permissions | The `execute` tool runs arbitrary shell commands that can read/write any path, bypassing file-level permission checks. |

### 16.3 Execute and Permissions Interaction

Permissions are explicitly **not supported** with backends that provide command execution,
unless all permission paths are scoped to composite backend routes:

```python
if (
    _permissions
    and isinstance(self.backend, BackendProtocol)
    and supports_execution(self.backend)
    and not _all_paths_scoped_to_routes(_permissions, self.backend)
):
    raise NotImplementedError(
        "FilesystemMiddleware does not yet support permissions with backends that "
        "provide command execution (SandboxBackendProtocol). ..."
    )
```

### 16.4 What Breaks if FilesystemMiddleware Is Removed

If `FilesystemMiddleware` were somehow excluded (bypassing the `ValueError`):

1. **All 7 filesystem tools disappear** -- the agent has no file read/write/edit capability.
2. **No execution capability** -- even if the backend supports it.
3. **Permission enforcement is lost** -- no path-based access control.
4. **Large result eviction is lost** -- execute outputs can overflow context.
5. **HumanMessage eviction is lost** -- large user messages can overflow context.
6. **State tracking breaks** -- `FilesystemState.files` is not managed.
7. **System prompts missing** -- filesystem and execution instructions not injected.

---

## 17. Constants Reference

### 17.1 Numeric Constants

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| `NUM_CHARS_PER_TOKEN` | `4` | `filesystem.py` | Token estimation ratio |
| `_SYNC_GLOB_WORKERS` | `4` | `filesystem.py` | ThreadPoolExecutor worker count |
| `GLOB_TIMEOUT` | `10.0` | `filesystem.py` | Glob operation timeout (seconds) |
| `LINE_NUMBER_WIDTH` | `6` | `filesystem.py` | Width for line number formatting |
| `DEFAULT_READ_OFFSET` | `0` | `filesystem.py` | Default read_file offset |
| `DEFAULT_READ_LIMIT` | `100` | `filesystem.py` | Default read_file line limit |
| `snapshot_frequency` | `50` | `FilesystemState` | DeltaChannel snapshot interval |
| `max_execute_timeout` | `3600` | Constructor default | Max execute timeout (seconds) |
| `tool_token_limit_before_evict` | `20000` | Constructor default | Tool result eviction threshold (tokens) |
| `human_message_token_limit_before_evict` | `50000` | Constructor default | HumanMessage eviction threshold (tokens) |
| `head_lines` | `5` | `_create_content_preview` | Lines in head preview |
| `tail_lines` | `5` | `_create_content_preview` | Lines in tail preview |
| `4000` | chars | `_slice_read_file_tm` | Head-slice size for read_file overflow clipping |
| `1000` | chars | `_create_content_preview` | Per-line truncation limit in preview |
| `5000` | tokens | `_derive_overflow_clip_threshold_tokens` | Fallback overflow clip threshold |

### 17.2 String Constants

| Constant | Purpose |
|----------|---------|
| `EMPTY_CONTENT_WARNING` | Returned when read_file reads an empty file |
| `READ_FILE_TRUNCATION_MSG` | Appended when read_file result is truncated due to size |
| `TOO_LARGE_TOOL_MSG` | Template for evicted tool results (in `_message_eviction.py`) |
| `TOO_LARGE_HUMAN_MSG` | Template for evicted HumanMessages (in `filesystem.py`) |
| `FILESYSTEM_SYSTEM_PROMPT` | Pre-formatted filesystem system prompt |
| `EXECUTION_SYSTEM_PROMPT` | Execution-specific system prompt |

### 17.3 Collection Constants

| Constant | Type | Contents |
|----------|------|----------|
| `TOOLS_EXCLUDED_FROM_EVICTION` | `tuple` | `("ls", "glob", "grep", "read_file", "edit_file", "write_file")` |
| `_DEFAULT_FS_TOOL_OPS` | `dict` | Maps tool names to `"read"` or `"write"` operations |
| `_FS_WCMATCH_FLAGS` | `int` | `wcglob.BRACE \| wcglob.GLOBSTAR` |
| `_FS_TOOL_PATH_ARGS` | `dict` | Maps tool names to `(operation, path_arg, scope, pattern_arg)` tuples |

---

## 18. Knowledge Verification Questions

### Q1: What are the 8 filesystem tools provided by FilesystemMiddleware and which tool schemas do they use?

The 8 tools are:
1. `ls` -- `LsSchema` (path)
2. `read_file` -- `ReadFileSchema` (file_path, offset, limit)
3. `write_file` -- `WriteFileSchema` (file_path, content)
4. `edit_file` -- `EditFileSchema` (file_path, old_string, new_string, replace_all)
5. `glob` -- `GlobSchema` (pattern, path)
6. `grep` -- `GrepSchema` (pattern, path, glob, output_mode, max_count)
7. `delete` -- `DeleteSchema` (file_path)
8. `execute` -- `ExecuteSchema` (command, timeout)

Each schema is a Pydantic `BaseModel` subclass. Tools are created by private `_create_*_tool()`
factory methods in the constructor.

### Q2: How does the first-match-wins permission evaluation work, and what happens when no rule matches?

`_check_fs_permission` iterates through rules in order. For each rule, it checks if the
operation is in `rule.operations` and if the path matches any pattern in `rule.paths` using
`wcmatch.glob.globmatch` with `BRACE | GLOBSTAR` flags. The first matching rule's `mode`
is returned immediately. If no rule matches after all rules are exhausted, the function
returns `"allow"` -- this is a default-allow policy.

### Q3: What is the default token limit before a tool result is evicted, and which tools are exempt from eviction?

The default threshold is `tool_token_limit_before_evict = 20000` tokens, estimated at
`NUM_CHARS_PER_TOKEN = 4` characters per token (effective threshold: 80,000 characters).
The exempt tools are defined in `TOOLS_EXCLUDED_FROM_EVICTION = ("ls", "glob", "grep",
"read_file", "edit_file", "write_file")`. Only `execute` results are subject to eviction.

### Q4: How does `_create_content_preview` create the head+tail preview for evicted content?

The function splits content into lines. If total lines <= `head_lines + tail_lines` (default
5 + 5 = 10), all lines are shown (each truncated to 1000 characters) with line numbers.
Otherwise, it takes the first 5 lines, appends `"\n... [N lines truncated] ...\n"` (where N
is the count of omitted lines), then appends the last 5 lines. All lines are formatted with
line numbers via `format_content_with_line_numbers`.

### Q5: What is the difference between "exact" and "bulk" ToolScope in `_fs_interrupt.py`?

- **Exact scope:** For tools with a single, explicit path argument (`read_file`, `write_file`,
  `edit_file`). The interrupt predicate checks `_check_fs_permission` directly on the
  normalized path and fires if the result is `"interrupt"`.
- **Bulk scope:** For tools with pattern or directory arguments (`ls`, `glob`, `grep`). The
  predicate precomputes anchor paths from interrupt-mode rules and fires if the search path
  overlaps any anchor (via `_paths_overlap`). Missing paths fire unconditionally since the
  search could reach anywhere. For `glob`, the pattern argument is also checked via
  `_bulk_pattern_fires`.

### Q6: How does FilesystemMiddleware handle the execute tool when the backend doesn't support SandboxBackendProtocol?

In `wrap_model_call`, the middleware checks `supports_execution(backend)`. If the backend
does NOT implement `SandboxBackendProtocol`, the `execute` tool is filtered out of
`request.tools` before the model call. The agent then sees only 6 tools instead of 7.
The execution system prompt is also omitted.

### Q7: What security validations does `FilesystemPermission.__post_init__` perform on path patterns?

Three validations:
1. Every path must start with `"/"` -- relative paths are rejected.
2. No path may contain `".."` -- prevents directory traversal.
3. No path may contain `"~"` -- prevents home directory expansion.
Violations raise `ValueError`.

### Q8: How does HumanMessage eviction differ from tool result eviction in terms of thresholds and triggers?

HumanMessage eviction has a threshold of 50,000 tokens (vs 20,000 for tool results) and
is triggered in `wrap_model_call` before the model runs (vs `wrap_tool_call` after the tool
runs). HumanMessages are offloaded to `{conversation_history_prefix}/{uuid}.md` (vs
`{large_tool_results_prefix}/{tool_call_id}`). The state update uses atomic `Overwrite` for
`DeltaChannel` compatibility. Already-evicted messages are tracked via `lc_evicted_to` in
`additional_kwargs` to prevent re-eviction.

### Q9: How do subagents inherit or override filesystem permissions?

From `graph.py`: `subagent_permissions = spec.get("permissions", permissions)`. If the
subagent spec includes a `"permissions"` key, those rules **replace** the parent's entirely
(no merging). If omitted, the parent's rules are inherited unchanged. Each subagent gets its
own `FilesystemMiddleware` instance with its own `_permissions` parameter.

### Q10: Why is FilesystemMiddleware marked as REQUIRED and what error is raised if excluded?

`FilesystemMiddleware` is required because it provides all filesystem tools, permission
enforcement, context management (eviction), and execution capability. Without it, the agent
cannot read, write, or edit files, run commands, or manage context overflow. `create_deep_agent`
raises `ValueError` if `FilesystemMiddleware` is not present in the middleware stack.

---

## Appendix A: Complete Method Reference for FilesystemMiddleware

| Method | Sync/Async | Purpose |
|--------|-----------|---------|
| `__init__` | Sync | Constructor; creates tools, sets thresholds |
| `_build_dynamic_system_prompt` | Sync | Builds and caches system prompt |
| `_get_backend` | Sync | Resolves backend from runtime |
| `_get_backend_from_runtime` | Sync | Resolves backend from state and runtime |
| `_create_ls_tool` | Sync | Factory for ls tool |
| `_create_read_file_tool` | Sync | Factory for read_file tool |
| `_create_write_file_tool` | Sync | Factory for write_file tool |
| `_create_edit_file_tool` | Sync | Factory for edit_file tool |
| `_create_glob_tool` | Sync | Factory for glob tool |
| `_create_grep_tool` | Sync | Factory for grep tool |
| `_create_execute_tool` | Sync | Factory for execute tool |
| `wrap_model_call` | Sync | Pre-model hook: prompts, tools, eviction |
| `awrap_model_call` | Async | Async variant of wrap_model_call |
| `wrap_tool_call` | Sync | Post-tool hook: eviction for non-exempt tools |
| `awrap_tool_call` | Async | Async variant of wrap_tool_call |
| `_process_large_message` | Sync | Evaluate and offload large tool result |
| `_aprocess_large_message` | Async | Async variant |
| `_check_eviction_needed` | Sync | Scan messages for eviction candidates |
| `_evict_and_truncate_messages` | Sync | Perform HumanMessage eviction |
| `_aevict_and_truncate_messages` | Async | Async variant |
| `_intercept_large_tool_result` | Sync | Entry point for tool result eviction |
| `_aintercept_large_tool_result` | Async | Async variant |
| `_apply_eviction_and_truncate` | Static | Apply eviction result to message list |
| `_unwrap_command_messages` | Static | Extract messages from Command wrapper |
| `_rewrap_command_messages` | Static | Re-wrap messages in Command/Overwrite |

## Appendix B: Module-Level Function Reference

### filesystem.py

| Function | Purpose |
|----------|---------|
| `_check_fs_permission(rules, operation, path)` | First-match-wins permission check |
| `_filter_paths_by_permission(rules, operation, paths)` | Filter path list by permissions |
| `_all_paths_scoped_to_routes(rules, backend)` | Check if all paths are within route scope |
| `_filter_file_infos_by_permission(rules, infos, operation)` | Filter FileInfo list |
| `_filter_grep_matches_by_permission(rules, matches, operation)` | Filter GrepMatch list |
| `_format_grep_tool_result(result, output_mode)` | Format grep output by mode |
| `_apply_permissions_to_ls_results(rules, entries)` | Filter ls directory entries |
| `_apply_permissions_to_glob_results(rules, matches)` | Filter glob matches |
| `_glob_timeout_message()` | Generate glob timeout error message |
| `_discard_task_result(task)` | Discard a completed Future result silently |
| `_file_data_reducer(left, right)` | Non-delta file state merger |
| `_file_data_delta_reducer(left, values)` | Delta-based file state merger |
| `supports_execution(backend)` | Check SandboxBackendProtocol support |
| `_build_evicted_human_content(message, replacement_text)` | Build evicted HumanMessage content |
| `_build_truncated_human_message(message, file_path)` | Build replacement HumanMessage |
| `_route_host_path_prompt(backend)` | Build virtual-to-host path mapping prompt |

### _fs_interrupt.py

| Function | Purpose |
|----------|---------|
| `_make_fs_when_predicate(rules, operation, path_arg, scope, pattern_arg)` | Dispatcher for predicate creation |
| `_make_exact_when_predicate(rules, operation, path_arg)` | Predicate for exact-scope tools |
| `_make_bulk_when_predicate(rules, operation, path_arg, pattern_arg)` | Predicate for bulk-scope tools |
| `_bulk_pattern_fires(raw_pattern, interrupt_anchors)` | Check glob pattern against interrupt anchors |
| `_build_interrupt_on_from_permissions(rules)` | Convert permissions to InterruptOnConfig |

### _message_eviction.py

| Function | Purpose |
|----------|---------|
| `_create_content_preview(content_str, head_lines, tail_lines)` | Head+tail preview generation |
| `_extract_text_from_message(message)` | Extract text from message content blocks |
| `_build_evicted_content(message, replacement_text)` | Build replacement content (preserves media) |
| `_build_evicted_tool_message(message, evicted_content)` | Build replacement ToolMessage |
| `_offload_tool_message_content(message, content_str, backend, prefix)` | Sync offload to filesystem |
| `_aoffload_tool_message_content(message, content_str, backend, prefix)` | Async offload to filesystem |

### _overflow_clip.py

| Function | Purpose |
|----------|---------|
| `_derive_overflow_clip_threshold_tokens(keep, max_input_tokens)` | Derive clip threshold from config |
| `_find_tail_tool_message_batch(messages)` | Find trailing ToolMessage batch |
| `_build_tool_call_index(messages)` | Map tool_call_id to tool_call dicts |
| `_slice_read_file_tm(msg, original_path)` | Head-slice read_file result to 4000 chars |
| `_read_file_original_path(msg, tc_index)` | Recover original file_path from tool call |
| `_clip_one_tail_message(msg, tc_index, backend, prefix)` | Sync clip single tail message |
| `_aclip_one_tail_message(msg, tc_index, backend, prefix)` | Async clip single tail message |
| `_clip_overflow_tail(preserved_messages, backend, ...)` | Sync overflow clipping entry point |
| `_aclip_overflow_tail(preserved_messages, backend, ...)` | Async overflow clipping entry point |

## Appendix C: Cross-Module Dependency Graph

```
filesystem.py (main middleware)
    |
    +---> _message_eviction.py (shared eviction primitives)
    |         Imports: TOO_LARGE_TOOL_MSG, _aoffload_tool_message_content,
    |                  _create_content_preview, _extract_text_from_message,
    |                  _offload_tool_message_content
    |
    +---> _fs_interrupt.py (human-in-the-loop bridge)
    |         Imports from filesystem.py: FilesystemOperation,
    |                  FilesystemPermission, _check_fs_permission
    |         Imports from backends.utils: _glob_anchor, _paths_overlap,
    |                  to_posix_path, validate_path
    |
    +---> _overflow_clip.py (context overflow fallback)
              Imports from _message_eviction.py: _aoffload_tool_message_content,
                       _extract_text_from_message, _offload_tool_message_content
              Used by: SummarizationMiddleware (not FilesystemMiddleware directly)
```

The dependency flow is unidirectional: `filesystem.py` imports from `_message_eviction.py`,
`_fs_interrupt.py` imports from `filesystem.py`, and `_overflow_clip.py` imports from
`_message_eviction.py`. There are no circular dependencies.

## Appendix D: Key Source Files

| File | Description |
|------|-------------|
| `libs/deepagents/deepagents/middleware/filesystem.py` | Main `FilesystemMiddleware` (~2,377 lines) |
| `libs/deepagents/deepagents/middleware/_fs_interrupt.py` | Permission-to-interrupt bridge (~182 lines) |
| `libs/deepagents/deepagents/middleware/_message_eviction.py` | Shared eviction primitives (~162 lines) |
| `libs/deepagents/deepagents/middleware/_overflow_clip.py` | Context overflow clipping (~206 lines) |
| `libs/deepagents/deepagents/backends/protocol.py` | `BackendProtocol` and `SandboxBackendProtocol` |
| `libs/deepagents/deepagents/backends/state.py` | `StateBackend` (default ephemeral backend) |
| `libs/deepagents/deepagents/graph.py` | `create_deep_agent` assembly, `_REQUIRED_MIDDLEWARE` |

---

*This is Doc 12 of the Deep Agents documentation set. For related middleware documentation,
see Doc 11 (Middleware Architecture), Doc 13 (Context Management), and Doc 16 (Permissions
and Human-in-the-Loop).*
