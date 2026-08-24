# 15 -- Permissions Middleware

> Primary source: `libs/deepagents/deepagents/middleware/permissions.py` (5 lines -- re-export shim)
> Implementation: `libs/deepagents/deepagents/middleware/filesystem.py` (2378 lines, `FilesystemPermission` dataclass + enforcement helpers)
> Interrupt bridge: `libs/deepagents/deepagents/middleware/_fs_interrupt.py` (183 lines)
> Graph assembly: `libs/deepagents/deepagents/graph.py` (`permissions` parameter on `create_deep_agent`)
> Utility helpers: `libs/deepagents/deepagents/backends/utils.py` (`validate_path`, `_glob_anchor`, `_paths_overlap`, `to_posix_path`)

---

## 1. Purpose

The permissions system is the final gatekeeper for filesystem operations in the
Deep Agents middleware stack. It controls which filesystem operations an agent
may perform and on which paths, implementing a rule-based allow/deny/interrupt
model that:

- **Denies** operations on protected paths, returning a permission error to the
  LLM without executing the tool.
- **Interrupts** operations on sensitive paths, pausing execution for human
  approval via `HumanInTheLoopMiddleware`.
- **Allows** all other operations (the default when no rule matches).

The permissions system is not a standalone middleware class. Instead, permission
enforcement is a cross-cutting concern that spans three components:

1. **`FilesystemPermission`** -- a dataclass representing a single access-control
   rule, defined in `deepagents.middleware.filesystem` (line 89).
2. **`FilesystemMiddleware`** -- the middleware that injects the filesystem tools
   (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`) and enforces
   `deny`-mode rules directly in each tool's implementation (line 751).
3. **`_fs_interrupt.py`** -- a bridge module that converts `interrupt`-mode
   permission rules into `interrupt_on` configurations consumed by
   `HumanInTheLoopMiddleware`.

Permissions are enforced at the tool level inside `FilesystemMiddleware`, not at
the backend level. This means direct backend usage (outside the tool boundary)
does not currently incorporate permission rules.

### The `permissions.py` Shim

The file `middleware/permissions.py` is a backward-compatible re-export:

```python
# middleware/permissions.py (lines 1-5)
"""Backward-compatible re-export for filesystem permissions."""

from deepagents.middleware.filesystem import FilesystemPermission

__all__ = ["FilesystemPermission"]
```

`FilesystemPermission` was originally defined in this module and later moved to
`filesystem.py`. The re-export preserves import compatibility. The class is also
re-exported from the package's public API via `deepagents.middleware.__init__`
(line 51):

```python
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission
```

All actual logic lives in `middleware/filesystem.py` (the `FilesystemPermission`
dataclass, the `_check_fs_permission` function, and the per-tool enforcement
code) and `middleware/_fs_interrupt.py` (the interrupt-to-HITL bridge).

---

## 2. Position in the Middleware Stack

`create_deep_agent()` assembles middleware into a layered stack. The stack has
three segments: a **base stack**, a **user middleware** insertion point, and a
**tail stack**. Permissions are enforced at two distinct positions within this
arrangement.

### 2.1 Base Stack (Tool Injection and Deny Enforcement)

`FilesystemMiddleware` sits in the base stack. It receives the `_permissions`
list at construction time and uses it for two purposes:

- **Pre-execution deny checks** -- before every tool call, the tool
  implementation calls `_check_fs_permission()`. If the result is `"deny"`, the
  tool returns an error immediately without touching the backend.
- **Post-execution result filtering** -- after bulk operations (`ls`, `glob`,
  `grep`), results are filtered to remove entries whose paths match deny rules.

The base stack ordering (from `graph.py`):

```
SkillsMiddleware             (if skills is provided)
FilesystemMiddleware         <-- deny enforcement lives here
SubAgentMiddleware           (if inline subagents exist)
SummarizationMiddleware
PatchToolCallsMiddleware
AsyncSubAgentMiddleware      (if async subagents exist)

(There is no TodoListMiddleware in the default stack.)
```

### 2.2 Tail Stack (Interrupt Enforcement and Tool Exclusion)

Interrupt-mode rules require `HumanInTheLoopMiddleware`, which is appended at
the very end of the tail stack. The tail stack is where the two "tail"
middleware live -- `_ToolExclusionMiddleware` and (conditionally)
`HumanInTheLoopMiddleware`. Both must run after all tool-injecting middleware
so they can observe the final, fully-assembled tool set.

The tail stack ordering (from `graph.py`, lines 793-814):

```
HarnessProfile extra_middleware
_ToolExclusionMiddleware     (if profile has excluded_tools)
AnthropicPromptCachingMiddleware
MemoryMiddleware             (if memory is provided)
HumanInTheLoopMiddleware     <-- interrupt enforcement lives here
```

`HumanInTheLoopMiddleware` is only installed when there are interrupt sources --
either explicit `interrupt_on` arguments or interrupt-mode permission rules.
The bridge module `_fs_interrupt.py` generates the `interrupt_on` configuration
from permission rules, and `graph.py` merges it with any user-supplied
`interrupt_on` (lines 809-814):

```python
# graph.py, lines 809-814
main_interrupt_on = _merge_fs_interrupt_on(
    _build_interrupt_on_from_permissions(permissions or []),
    interrupt_on,
)
if main_interrupt_on is not None:
    deepagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=main_interrupt_on))
```

### 2.3 The `_ToolExclusionMiddleware` Companion

`_ToolExclusionMiddleware` (defined in `middleware/_tool_exclusion.py`) is the
other tail-stack middleware. It removes tools that a `HarnessProfile` marks as
excluded. It is placed late in the stack so it can strip middleware-injected
tools (filesystem, subagent, etc.) that the profile excludes. From
`_tool_exclusion.py`, lines 31-54:

```python
class _ToolExclusionMiddleware(AgentMiddleware[Any, Any, Any]):
    """Middleware that filters excluded tools from the model request.

    Should be placed late in the middleware stack (after all
    tool-injecting middleware) so it can strip middleware-injected tools
    (filesystem, subagent, etc.) that the harness profile marks as excluded.
    """

    def __init__(self, *, excluded: frozenset[str]) -> None:
        self._excluded = excluded

    def wrap_model_call(self, request, handler):
        if self._excluded:
            filtered = [t for t in request.tools if _tool_name(t) not in self._excluded]
            request = request.override(tools=filtered)
        return handler(request)
```

Both tail-stack middleware share the requirement that they must see the final
tool set. `_ToolExclusionMiddleware` ensures the model does not see excluded
tools; `HumanInTheLoopMiddleware` ensures interrupt-mode permission rules
trigger human approval before tool execution.

---

## 3. The `FilesystemPermission` Dataclass

Defined at `filesystem.py`, lines 89-123:

```python
@dataclass
class FilesystemPermission:
    """A single access rule for filesystem operations."""

    operations: list[FilesystemOperation]
    paths: list[str]
    mode: Literal["allow", "deny", "interrupt"] = "allow"
```

### 3.1 Fields

| Field | Type | Description |
|-------|------|-------------|
| `operations` | `list[FilesystemOperation]` | Which operations this rule applies to. `FilesystemOperation` is `Literal["read", "write"]` (line 77). |
| `paths` | `list[str]` | Glob patterns for paths this rule covers. Each must start with `"/"`. Supports `*`, `**`, `?`, and brace expansion via `wcmatch.glob`. |
| `mode` | `Literal["allow", "deny", "interrupt"]` | The effect when a tool call matches. Defaults to `"allow"`. |

### 3.2 Path Validation

The `__post_init__` method (lines 111-123) validates every path pattern:

```python
def __post_init__(self) -> None:
    """Validate permission path patterns."""
    for path in self.paths:
        if not path.startswith("/"):
            msg = f"Permission path must start with '/': {path!r}"
            raise ValueError(msg)
        parts = PurePosixPath(path.replace("\\", "/")).parts
        if ".." in parts:
            msg = f"Permission path must not contain '..': {path!r}"
            raise ValueError(msg)
        if "~" in parts:
            msg = f"Permission path must not contain '~': {path!r}"
            raise NotImplementedError(msg)
```

Three invariants are enforced:

1. Every path pattern must begin with `/` (absolute paths only).
2. Path traversal via `..` is forbidden -- raises `ValueError`.
3. Home-directory expansion via `~` is not implemented -- raises
   `NotImplementedError`.

### 3.3 Operation Type

`FilesystemOperation` is defined at line 77:

```python
FilesystemOperation = Literal["read", "write"]
```

The mapping from filesystem tool names to their operation types is at line 79:

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

The `execute` tool is intentionally absent. Permissions are not supported with
execution-capable backends unless all permission paths are scoped to composite
backend routes (see Section 9).

### 3.4 Permission Modes

| Mode | Effect | Enforcement Point |
|------|--------|-------------------|
| `allow` | Call proceeds normally | Default when no rule matches |
| `deny` | Tool returns `"Error: permission denied"` immediately | Inside each tool's sync/async handler in `FilesystemMiddleware` |
| `interrupt` | Call pauses for human approval via `HumanInTheLoopMiddleware` | Via `_fs_interrupt.py` bridge, before the tool executes |

The `interrupt` mode is documented with this important caveat in the source
(lines 96-109):

> Best paired with patterns that have a literal leading anchor (e.g.,
> `/secrets/**`, `/projects/*/secrets/**`). Bulk tools (`ls`/`glob`/`grep`)
> fire the interrupt based on whether their search subtree could overlap
> the rule's anchored prefix, so a fully unanchored pattern (`/**/secrets`)
> collapses to `/` and conservatively over-fires for any bulk call.

---

## 4. Permission Evaluation: `_check_fs_permission()`

### 4.1 The Core Check

The core evaluation function is at `filesystem.py`, lines 126-136:

```python
def _check_fs_permission(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path: str,
) -> Literal["allow", "deny", "interrupt"]:
    for rule in rules:
        if operation not in rule.operations:
            continue
        if any(wcglob.globmatch(path, pattern, flags=_FS_WCMATCH_FLAGS) for pattern in rule.paths):
            return rule.mode
    return "allow"
```

### 4.2 First-Match-Wins Semantics

Rules are evaluated in declaration order. The first rule whose `operations`
field contains the requested operation AND whose `paths` list contains a
pattern matching the requested path determines the outcome. If no rule matches,
the default is `"allow"`.

This means rule ordering is critical. A deny rule placed before an allow rule
for the same path will block access; reversing the order will allow it.

Example -- ordering determines behavior:

```python
# The deny rule fires first; the interrupt never triggers for /secrets/**
permissions = [
    FilesystemPermission(operations=["read"], paths=["/secrets/**"], mode="deny"),
    FilesystemPermission(operations=["read"], paths=["/secrets/**"], mode="interrupt"),
]

# The interrupt fires first; human approval is required
permissions = [
    FilesystemPermission(operations=["read"], paths=["/secrets/**"], mode="interrupt"),
    FilesystemPermission(operations=["read"], paths=["/secrets/**"], mode="deny"),
]
```

### 4.3 Glob Matching

Pattern matching uses `wcmatch.glob.globmatch` with the flags
`BRACE | GLOBSTAR` (line 74):

```python
_FS_WCMATCH_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR
```

- `BRACE` enables brace expansion (e.g., `*.{py,js}`).
- `GLOBSTAR` enables `**` to match zero or more directory levels.

Examples of matching behavior:

| Pattern | Matches | Does Not Match |
|---------|---------|----------------|
| `/secrets/**` | `/secrets/key.txt`, `/secrets/sub/key.txt` | `/secret/key.txt` |
| `/workspace/*.py` | `/workspace/main.py` | `/workspace/sub/main.py` |
| `/**/*.log` | `/app/debug.log`, `/a/b/c.log` | `/app/debug.txt` |
| `/data/{csv,json}/**` | `/data/csv/file.csv`, `/data/json/file.json` | `/data/xml/file.xml` |

---

## 5. Permission Modes in Detail

### 5.1 Allow Mode

When `_check_fs_permission()` returns `"allow"`, the tool call proceeds
normally. This is both the explicit mode for allow rules and the implicit
default when no rule matches.

### 5.2 Deny Mode

When `_check_fs_permission()` returns `"deny"`, the tool implementation
returns an error `ToolMessage` immediately without executing the backend
operation. The error message follows the pattern:

```
Error: permission denied for {operation} on {validated_path}
```

Deny enforcement happens at two levels within `FilesystemMiddleware`:

**Pre-execution check** -- every tool function validates permissions before
calling the backend. For example, in the `ls` tool (lines 962-968):

```python
if _check_fs_permission(self._permissions, "read", validated_path) == "deny":
    return ToolMessage(
        content=f"Error: permission denied for read on {validated_path}",
        name="ls",
        tool_call_id=runtime.tool_call_id,
        status="error",
    )
```

This pattern is repeated in `read_file` (line 1154), `write_file` (line 1221),
`edit_file` (line 1315), `glob` (line 1408), and `grep` (line 1586). The
per-tool enforcement locations:

| Tool | Operation | Pre-Check Line (sync) | Pre-Check Line (async) |
|------|-----------|----------------------|------------------------|
| `ls` | `"read"` | 962 | 1001 |
| `read_file` | `"read"` | 1154 | 1181 |
| `write_file` | `"write"` | 1221 | 1260 |
| `edit_file` | `"write"` | 1315 | 1357 |
| `glob` | `"read"` | 1408 | 1504 |
| `grep` | `"read"` | 1586 | 1629 |

**Post-execution result filtering** -- for bulk operations that return
multiple paths, denied paths are removed from results. This prevents an agent
from discovering the existence of denied files through bulk queries. Three
filtering helpers are used:

```python
# filesystem.py, lines 139-155
def _filter_paths_by_permission(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    paths: list[str],
) -> list[str]:
    """Filter paths, removing only those denied by a rule.

    Interrupt-mode paths pass through here: the interrupt fires at the HITL
    stage *before* the tool runs (see `_build_interrupt_on_from_permissions`
    and its scope-aware predicate), so by the time result-filtering runs the
    user has already approved (or no rule matched). Filtering interrupt-mode
    results out here would silently empty the listing the user just approved.
    """
    if not rules:
        return paths
    return [p for p in paths if _check_fs_permission(rules, operation, p) != "deny"]
```

There are three specialized filter functions for different result types:

| Function | Line | Filters |
|----------|------|---------|
| `_filter_paths_by_permission` | 139 | Plain path strings |
| `_filter_file_infos_by_permission` | 175 | `FileInfo` dicts (from `ls`, `glob`) |
| `_filter_grep_matches_by_permission` | 189 | `GrepMatch` dicts (from `grep`) |

All three filter ONLY `deny` results. Interrupt-mode paths pass through result
filtering because interrupt approval happens at the HITL stage before the tool
runs. The code comments make this reasoning explicit.

Two convenience wrappers combine filtering with path extraction:

```python
# filesystem.py, lines 218-233
def _apply_permissions_to_ls_results(rules, entries):
    """Filter ls entries by permission and return their paths."""
    filtered_entries = _filter_file_infos_by_permission(rules, entries, operation="read")
    return [fi.get("path", "") for fi in filtered_entries]

def _apply_permissions_to_glob_results(rules, matches):
    """Filter glob matches by permission and return their paths."""
    filtered_infos = _filter_file_infos_by_permission(rules, matches, operation="read")
    return [fi.get("path", "") for fi in filtered_infos]
```

### 5.3 Interrupt Mode

When `_check_fs_permission()` returns `"interrupt"`, the tool call should pause
for human approval. This mode is not enforced within `FilesystemMiddleware`
itself -- instead, the interrupt bridge module generates `interrupt_on`
configurations that `HumanInTheLoopMiddleware` consumes. This separation exists
because `FilesystemMiddleware` does not know about the HITL system; the
module docstring of `_fs_interrupt.py` states this explicitly:

> `FilesystemMiddleware` itself doesn't know about HITL -- it only enforces deny
> rules and filters denied results.

When a tool call matches an interrupt rule, execution pauses and the human
reviewer is presented with four decision options (from `_fs_interrupt.py`,
line 173):

```python
allowed: list[Literal["approve", "edit", "reject", "respond"]] = [
    "approve", "edit", "reject", "respond"
]
```

- **approve** -- allow the call to proceed as-is.
- **edit** -- modify the tool call arguments before re-entering the tool.
  The tool's deny check runs again on the edited arguments, so the human
  cannot accidentally bypass a deny rule via the edit action.
- **reject** -- block the call.
- **respond** -- skip execution and provide a text response instead.

---

## 6. The Interrupt Bridge: `_fs_interrupt.py`

This module converts interrupt-mode permission rules into `interrupt_on`
configurations for `HumanInTheLoopMiddleware`. It lives at
`libs/deepagents/deepagents/middleware/_fs_interrupt.py` (183 lines).

### 6.1 Module-Level Documentation

The module docstring (lines 1-8) summarizes the design:

```python
"""Glue between `FilesystemPermission` rules and `HumanInTheLoopMiddleware`.

`FilesystemMiddleware` itself doesn't know about HITL -- it only enforces deny
rules and filters denied results. The graph-assembly code in
`deepagents.graph` calls `_build_interrupt_on_from_permissions` to turn the
filesystem permissions into an `interrupt_on` mapping for
`HumanInTheLoopMiddleware`, using a `when` predicate that decides per call
whether the access intersects an interrupt-mode rule.
"""
```

### 6.2 Tool Scope Classification

The bridge classifies each filesystem tool by its "scope" -- how the tool's
path argument relates to the files it accesses (line 31):

```python
ToolScope = Literal["exact", "bulk"]
```

- **exact** -- the tool operates on exactly the named path. A single file read
  or write. Interrupt fires if and only if the exact path matches an
  interrupt-mode rule.
- **bulk** -- the tool's path argument names a search root and the call may
  surface any descendant. Interrupt fires when the search subtree intersects
  an interrupt-mode rule's pattern. When the path argument is omitted (e.g.,
  `grep(path=None)`), the interrupt fires unconditionally for any interrupt-mode
  rule, since a pathless bulk call can touch anything.

The mapping is defined at lines 38-45:

```python
_FS_TOOL_PATH_ARGS: dict[str, tuple[FilesystemOperation, str, ToolScope, str | None]] = {
    "ls": ("read", "path", "bulk", None),
    "read_file": ("read", "file_path", "exact", None),
    "write_file": ("write", "file_path", "exact", None),
    "edit_file": ("write", "file_path", "exact", None),
    "glob": ("read", "path", "bulk", "pattern"),
    "grep": ("read", "path", "bulk", None),
}
```

Each entry maps a tool name to a tuple of:
`(operation, path_arg_name, scope, pattern_arg_name)`.

The fourth element (`pattern_arg_name`) is non-`None` only for `glob`, whose
`pattern` argument can independently redirect the search root. An absolute glob
pattern ignores the `path` argument entirely.

| Scope | Tools | Interrupt Behavior |
|-------|-------|--------------------|
| `exact` | `read_file`, `write_file`, `edit_file` | Fires if and only if the exact path matches an interrupt-mode rule |
| `bulk` | `ls`, `glob`, `grep` | Fires if the search subtree could overlap an interrupt-mode rule's prefix |

### 6.3 Predicate Construction

The bridge generates a `when` predicate for each tool that determines
per-invocation whether the interrupt should fire.

**Exact predicates** (`_make_exact_when_predicate`, lines 75-88):

For exact-scope tools, the predicate validates and normalizes the call's path
argument, then calls `_check_fs_permission()`. The interrupt fires only when the
permission check returns `"interrupt"`. If a preceding deny rule matches
first (first-match-wins), the deny takes priority and the interrupt does not
fire -- the tool returns a permission-denied error instead.

```python
# _fs_interrupt.py, lines 75-88
def _make_exact_when_predicate(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path_arg_name: str,
) -> Callable[[ToolCallRequest], bool]:
    def when(req: ToolCallRequest) -> bool:
        raw_path = req.tool_call.get("args", {}).get(path_arg_name)
        if not isinstance(raw_path, str):
            return False
        try:
            normalized = validate_path(raw_path)
        except ValueError:
            return False
        return _check_fs_permission(rules, operation, normalized) == "interrupt"
    return when
```

**Bulk predicates** (`_make_bulk_when_predicate`, lines 93-136):

Bulk predicates are more complex. They precompute the anchors of all
interrupt-mode rules for the relevant operation at construction time. At call
time:

1. If no interrupt anchors exist, return `False`.
2. If the path argument is missing (`None`), fire unconditionally -- the call
   could touch any file.
3. Normalize `"."` paths to `"/"` to prevent bypass via `path="."`.
4. Check whether the call's path overlaps any interrupt anchor using
   `_paths_overlap()`.
5. For `glob`, additionally check whether the `pattern` argument reaches an
   interrupt-mode subtree.

```python
# _fs_interrupt.py, lines 93-136 (abbreviated)
def _make_bulk_when_predicate(
    rules: list[FilesystemPermission],
    operation: FilesystemOperation,
    path_arg_name: str,
    pattern_arg_name: str | None = None,
) -> Callable[[ToolCallRequest], bool]:
    # Precompute interrupt-mode rule anchors
    interrupt_anchors: list[str] = [
        _glob_anchor(pattern) for rule in rules
        if rule.mode == "interrupt" and operation in rule.operations
        for pattern in rule.paths
    ]

    def when(req: ToolCallRequest) -> bool:
        if not interrupt_anchors:
            return False
        args = req.tool_call.get("args", {})
        raw_path = args.get(path_arg_name)
        if not isinstance(raw_path, str):
            return raw_path is None  # Missing path -> fire unconditionally
        try:
            normalized = validate_path(raw_path)
        except ValueError:
            return False
        if normalized == "/.":
            normalized = "/"
        if any(_paths_overlap(normalized, anchor) for anchor in interrupt_anchors):
            return True
        # Check glob pattern argument if applicable
        if pattern_arg_name is not None:
            raw_pattern = args.get(pattern_arg_name)
            if isinstance(raw_pattern, str) and _bulk_pattern_fires(raw_pattern, interrupt_anchors):
                return True
        return False
    return when
```

### 6.4 Glob Pattern Bypass Prevention

The `_bulk_pattern_fires()` function (lines 139-152) handles a specific bypass
vector where `glob(pattern="/secrets/**", path="/workspace")` could bypass an
interrupt rule on `/secrets/**` if only the `path` argument were checked:

```python
# _fs_interrupt.py, lines 139-152
def _bulk_pattern_fires(raw_pattern: str, interrupt_anchors: list[str]) -> bool:
    """Whether a glob `pattern` reaches an interrupt-mode subtree regardless of `path`."""
    posix_pattern = to_posix_path(raw_pattern)
    if posix_pattern.startswith("/"):
        return any(_paths_overlap(_glob_anchor(raw_pattern), anchor)
                   for anchor in interrupt_anchors)
    return ".." in PurePosixPath(posix_pattern).parts
```

An absolute pattern is checked against interrupt anchors by its own root. A
relative pattern containing `..` can climb out of the `path`, so it is treated
as unconditionally firing.

### 6.5 Utility Functions from `backends/utils.py`

The interrupt bridge depends on several utility functions:

**`_glob_anchor(pattern)`** (utils.py, line 404): Returns the longest leading
directory of a pattern with no wildcards. For `/secrets/**` it returns
`/secrets`; for `/a/*/b` it returns `/a`. Patterns with wildcards at or near
the root (e.g., `/**/secrets`) collapse to `/`, causing conservative
over-gating.

**`_paths_overlap(call_path, rule_anchor)`** (utils.py, line 425): Returns
`True` if two subtrees intersect -- i.e., one path is a component-wise prefix
of the other, or they are equal. The root `/` overlaps everything. Comparison
uses `PurePosixPath` components, so `/secret` does not overlap `/secrets`.

```python
# backends/utils.py, lines 425-434
def _paths_overlap(call_path: str, rule_anchor: str) -> bool:
    a = PurePosixPath(call_path)
    b = PurePosixPath(rule_anchor)
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)
```

**`to_posix_path(path)`** (utils.py, line 437): Normalizes backslash separators
to forward slashes for `PurePosixPath` use. Required because backends on
Windows return OS-native paths using backslashes.

**`validate_path(path)`** (utils.py, line 461): Validates and normalizes file
paths for security. Prevents directory traversal attacks and enforces consistent
formatting. All paths are normalized to use forward slashes and start with a
leading slash.

### 6.6 Entry Point: `_build_interrupt_on_from_permissions()`

This function (lines 155-182) is the public entry point called by `graph.py`.
It returns a `dict[str, InterruptOnConfig]` with an entry for each filesystem
tool whose operation is covered by at least one interrupt-mode rule:

```python
# _fs_interrupt.py, lines 155-182
def _build_interrupt_on_from_permissions(
    rules: list[FilesystemPermission],
) -> dict[str, InterruptOnConfig]:
    if not any(r.mode == "interrupt" for r in rules):
        return {}

    allowed: list[Literal["approve", "edit", "reject", "respond"]] = [
        "approve", "edit", "reject", "respond"
    ]
    result: dict[str, InterruptOnConfig] = {}
    for tool_name, (op, arg, scope, pattern_arg) in _FS_TOOL_PATH_ARGS.items():
        if not any(r.mode == "interrupt" and op in r.operations for r in rules):
            continue
        result[tool_name] = InterruptOnConfig(
            allowed_decisions=allowed,
            when=_make_fs_when_predicate(rules, op, arg, scope, pattern_arg),
        )
    return result
```

The function short-circuits immediately when no interrupt-mode rules exist,
avoiding unnecessary predicate construction.

---

## 7. How Permissions Interact with Filesystem Tools

Each filesystem tool in `FilesystemMiddleware` follows the same permission
enforcement pattern:

1. **Validate the path** -- call `validate_path()` to normalize and sanitize
   the input path.
2. **Check deny** -- call `_check_fs_permission(self._permissions, operation, path)`.
   If the result is `"deny"`, return an error `ToolMessage`.
3. **Execute the backend operation** -- call the appropriate backend method.
4. **Filter results** (bulk tools only) -- for `ls`, `glob`, and `grep`, pass
   the results through the appropriate permission filter to remove denied
   entries.

Note that the tool implementations check only for `"deny"` mode. The
`"interrupt"` mode is handled at a higher level by `HumanInTheLoopMiddleware`,
which intercepts the tool call before it reaches the tool implementation. By the
time a tool function runs, the human has already approved an interrupt-mode
call.

### 7.1 Per-Tool Permission Enforcement

| Tool | Operation | Pre-Check (sync) | Result Filter |
|------|-----------|-------------------|---------------|
| `ls` | `"read"` | line 962 | `_apply_permissions_to_ls_results()` (line 978) |
| `read_file` | `"read"` | line 1154 | None (single file) |
| `write_file` | `"write"` | line 1221 | None (single file) |
| `edit_file` | `"write"` | line 1315 | None (single file) |
| `glob` | `"read"` | line 1408 | `_apply_permissions_to_glob_results()` (line 1480) |
| `grep` | `"read"` | line 1586 | `_filter_grep_matches_by_permission()` (line 1596) |

### 7.2 Permission Storage in FilesystemMiddleware

The permissions list is stored as a private attribute initialized in `__init__`
(line 879):

```python
self._permissions = list(_permissions or [])
```

The `_permissions` parameter is marked private (prefixed with `_`) in the
constructor signature because it is an internal implementation detail that may
move to the backend layer in a future change:

```python
# filesystem.py, lines 810-821 (constructor signature, abbreviated)
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

---

## 8. Configuration via `create_deep_agent()`

### 8.1 The `permissions` Parameter

The `permissions` parameter of `create_deep_agent()` accepts an optional list of
`FilesystemPermission` rules. From `graph.py`, line 245:

```python
def create_deep_agent(
    ...
    permissions: list[FilesystemPermission] | None = None,
    ...
)
```

The docstring for this parameter (lines 418-442) specifies:

> Rules are evaluated in declaration order; the first match wins.
> If no rule matches, the call is allowed.
>
> Subagents inherit these rules unless they specify their own
> `permissions` field, which replaces the parent's rules entirely.

### 8.2 Where Permissions Are Forwarded

When provided, the permissions list is passed to multiple places:

**The main agent's `FilesystemMiddleware`** (lines 756-762):

```python
deepagent_middleware.append(
    FilesystemMiddleware(
        backend=backend,
        custom_tool_descriptions=_profile.tool_description_overrides,
        _permissions=permissions,
    )
)
```

**The general-purpose subagent's `FilesystemMiddleware`** (lines 696-701):

```python
FilesystemMiddleware(
    backend=backend,
    custom_tool_descriptions=_profile.tool_description_overrides,
    _permissions=permissions,
)
```

**Each declarative `SubAgent`'s `FilesystemMiddleware`** (lines 616-625):

```python
subagent_permissions = spec.get("permissions", permissions)
subagent_middleware: list[...] = [
    ...
    FilesystemMiddleware(
        backend=backend,
        ...,
        _permissions=subagent_permissions,
    ),
    ...
]
```

**The `HumanInTheLoopMiddleware`** (via the interrupt bridge, lines 809-814):

```python
main_interrupt_on = _merge_fs_interrupt_on(
    _build_interrupt_on_from_permissions(permissions or []),
    interrupt_on,
)
if main_interrupt_on is not None:
    deepagent_middleware.append(
        HumanInTheLoopMiddleware(interrupt_on=main_interrupt_on)
    )
```

### 8.3 Subagent Permission Inheritance

Subagents inherit the parent agent's permissions by default. The inheritance
rule (line 616):

```python
subagent_permissions = spec.get("permissions", permissions)
```

A subagent can override permissions entirely by specifying its own `permissions`
field in its `SubAgent` spec. There is no merging -- the subagent's rules
replace the parent's rules completely.

`CompiledSubAgent` runnables do not inherit permissions. They must configure
their own permission behavior internally.

`AsyncSubAgent` specs do not inherit permissions. Any access control must be
configured on the remote subagent.

The interrupt configs for subagents are also derived from their permissions
(line 664-667):

```python
subagent_interrupt_on = spec.get("interrupt_on", interrupt_on)
subagent_interrupt_on = _merge_fs_interrupt_on(
    _build_interrupt_on_from_permissions(subagent_permissions or []),
    subagent_interrupt_on,
)
```

### 8.4 Merging with User-Supplied `interrupt_on`

When both filesystem-permission-derived interrupt configs and user-supplied
`interrupt_on` entries exist, they are merged by `_merge_fs_interrupt_on()`
(lines 188-203):

```python
# graph.py, lines 188-203
def _merge_fs_interrupt_on(
    fs_interrupt_on: dict[str, InterruptOnConfig],
    user_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
) -> dict[str, bool | InterruptOnConfig] | None:
    if not fs_interrupt_on and not user_interrupt_on:
        return None
    merged: dict[str, bool | InterruptOnConfig] = {**fs_interrupt_on}
    if user_interrupt_on:
        merged.update(user_interrupt_on)
    return merged
```

User-supplied entries override generated ones per tool name. If a user passes
`interrupt_on={"edit_file": True}` and permissions also generate an
`InterruptOnConfig` for `edit_file`, the user's `True` wins.

### 8.5 Usage Examples

**Deny access to a directory:**

```python
from deepagents.graph import create_deep_agent
from deepagents.middleware.filesystem import FilesystemPermission

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    permissions=[
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/secrets/**"],
            mode="deny",
        ),
    ],
)
```

Any tool call targeting a path under `/secrets/` returns an error. Bulk tools
like `ls` and `grep` silently exclude entries under `/secrets/` from results.

**Require approval for writes, allow reads:**

```python
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    permissions=[
        FilesystemPermission(
            operations=["write"],
            paths=["/production/**"],
            mode="interrupt",
        ),
        FilesystemPermission(
            operations=["read"],
            paths=["/production/**"],
            mode="allow",
        ),
    ],
)
```

Read operations under `/production/` proceed without interruption. Write
operations (`write_file`, `edit_file`) pause for human approval.

**Combined deny and interrupt rules:**

```python
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    permissions=[
        # Hard deny on credentials
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/config/credentials.json", "/config/.env"],
            mode="deny",
        ),
        # Interrupt on other config changes
        FilesystemPermission(
            operations=["write"],
            paths=["/config/**"],
            mode="interrupt",
        ),
        # Allow everything else
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/**"],
            mode="allow",
        ),
    ],
)
```

Because of first-match-wins evaluation:

1. Access to `/config/credentials.json` or `/config/.env` is always denied.
2. Write access to other files under `/config/` pauses for human approval.
3. All other operations are explicitly allowed by the catch-all rule (which
   matches the implicit default, but makes intent explicit).

---

## 9. Default Permission Behavior

When no `permissions` are specified (the default), the following behavior
applies:

- `self._permissions` is set to an empty list (`[]`) in `FilesystemMiddleware`
  (line 879):
  ```python
  self._permissions = list(_permissions or [])
  ```
- `_check_fs_permission()` iterates over zero rules and returns `"allow"` for
  every call.
- All result-filtering helpers short-circuit on empty rules. For example,
  `_filter_paths_by_permission()` (line 152):
  ```python
  if not rules:
      return paths
  ```
- `_build_interrupt_on_from_permissions([])` returns an empty dict, so no
  `HumanInTheLoopMiddleware` is installed for permissions (it may still be
  installed if the user passes `interrupt_on` directly).

In summary: **with no permission rules, all filesystem operations are
unrestricted.**

---

## 10. Integration with HarnessProfile

The `HarnessProfile` system interacts with permissions in several indirect ways.

### 10.1 Protected Scaffolding

`FilesystemMiddleware` is marked as required scaffolding in `graph.py`
(lines 206-227). It cannot be excluded via `HarnessProfile.excluded_middleware`:

```python
# graph.py, lines 206-221
_REQUIRED_MIDDLEWARE: tuple[tuple[type[AgentMiddleware[Any, Any, Any]], tuple[str, ...]], ...] = (
    (FilesystemMiddleware, ()),
    (SubAgentMiddleware, ()),
)
```

The docstring explains:

> Removing any of these silently breaks core features:
> `FilesystemMiddleware` backs every built-in file tool and now also enforces
> `permissions` rules (a security guarantee), while `SubAgentMiddleware` backs
> the `task` tool handler.

Attempting to exclude `FilesystemMiddleware` raises a `ValueError` from
`harness_profiles.py` (lines 74-79):

```
HarnessProfile.excluded_middleware is invalid:
  - required scaffolding cannot be excluded: FilesystemMiddleware
    (back filesystem tools, subagent dispatch, and permission
    enforcement -- use excluded_tools for per-tool visibility or
    adjust profile settings instead of stripping scaffolding)
```

The `_REQUIRED_MIDDLEWARE_CLASSES` and `_REQUIRED_MIDDLEWARE_NAMES` frozensets
(lines 223-233) are derived from `_REQUIRED_MIDDLEWARE` and used for quick
membership testing during validation.

### 10.2 Tool Exclusion Interaction

A `HarnessProfile` can exclude specific filesystem tools via `excluded_tools`.
The `_ToolExclusionMiddleware` removes these tools from the model request. This
interacts with permissions as follows:

- If a tool is excluded by the profile, the model never sees or calls it, so
  permission rules for that tool are effectively moot.
- However, the tool still exists in the middleware's tool registry. Exclusion
  happens at the model-request level, not at the middleware-construction level.
- The `_build_interrupt_on_from_permissions()` function still generates
  `InterruptOnConfig` entries for excluded tools, but those configs have no
  effect since the tool is never invoked.

### 10.3 Tool Description Overrides

A profile's `tool_description_overrides` are passed to `FilesystemMiddleware`
via the `custom_tool_descriptions` parameter and can customize how filesystem
tool descriptions appear to the model. This does not affect permission
enforcement.

### 10.4 The execute Tool Limitation

`FilesystemMiddleware` raises `NotImplementedError` if permissions are specified
alongside a backend that supports execution (`SandboxBackendProtocol`), unless
all permission paths are scoped to routes of a `CompositeBackend`
(lines 849-861):

```python
# filesystem.py, lines 849-861
if (
    _permissions
    and isinstance(self.backend, BackendProtocol)
    and supports_execution(self.backend)
    and not _all_paths_scoped_to_routes(_permissions, self.backend)
):
    msg = (
        "FilesystemMiddleware does not yet support permissions with backends that "
        "provide command execution (SandboxBackendProtocol). Tool-level permissions "
        "for the execute tool are not implemented. Either remove permissions or use "
        "a backend without execution support."
    )
    raise NotImplementedError(msg)
```

This exists because an agent with shell access via `execute` can bypass
filesystem permissions entirely (e.g., `execute(command="cat /secrets/key.txt")`).
Permission enforcement does not extend to shell commands.

The `_all_paths_scoped_to_routes` function (lines 157-172) checks that every
permission path falls under a `CompositeBackend` route prefix:

```python
# filesystem.py, lines 157-172
def _all_paths_scoped_to_routes(
    rules: list[FilesystemPermission],
    backend: BackendProtocol,
) -> bool:
    if not isinstance(backend, CompositeBackend):
        return False
    route_prefixes = list(backend.routes.keys())
    if not route_prefixes:
        return False
    for rule in rules:
        for path in rule.paths:
            if not any(path.startswith(prefix) for prefix in route_prefixes):
                return False
    return True
```

---

## 11. Security Considerations

### 11.1 Tool-Level Enforcement Only

Permissions are enforced at the tool boundary, not the backend level. Code that
calls the backend directly (outside the filesystem tools) bypasses permission
checks entirely. This is a deliberate design trade-off documented in the
`create_deep_agent` docstring:

> `FilesystemMiddleware` applies these permissions at the tool level for its
> built-in filesystem tools, not at the backend level. Direct backend usage
> does not currently incorporate `permissions`.

### 11.2 Path Normalization

All paths are validated and normalized through `validate_path()` before
permission checks. This prevents bypass via:

- Directory traversal (`..`).
- Home-directory expansion (`~`).
- Backslash path separators on Windows.
- Relative paths that avoid pattern matching.

The bulk-predicate code in `_fs_interrupt.py` additionally normalizes `"/."`
(the `validate_path` output for `"."`, `""`, and `"./"`) to `"/"` to prevent
agents from using `path="."` to bypass interrupt rules on bulk tools
(lines 122-124):

```python
# _fs_interrupt.py, lines 122-124
if normalized == "/.":
    normalized = "/"
```

The code comment explains the rationale:

> `validate_path` returns `/.` for current-directory aliases like
> `"."`, `""`, and `"./"`. Those refer to the whole accessible tree
> just like a missing path arg, so collapse to `/` so the
> root-overlaps-everything branch in `_paths_overlap` fires. Without
> this, an agent could pass `path="."` to bypass HITL.

### 11.3 Conservative Over-Firing for Interrupt Rules

Interrupt-mode rules with wildcard-heavy patterns (e.g., `/**/secrets`) collapse
to the root anchor `/` when processed by `_glob_anchor()`. This causes bulk
tools to fire the interrupt for any call, because the root overlaps every
subtree. The module documentation recommends using patterns with a literal
leading anchor (e.g., `/secrets/**`) for more precise gating.

### 11.4 Result Filtering vs. Existence Leakage

Deny rules filter paths from bulk operation results, but the results may still
reveal indirect information. For example, a `grep` search that returns 3 matches
where 5 exist (2 denied) reveals that matching content exists beyond what is
shown. This is an accepted trade-off; complete opacity would require refusing
the entire bulk operation when any denied path is in scope.

---

## 12. Key Source Files

| File | Lines | Description |
|------|-------|-------------|
| `libs/deepagents/deepagents/middleware/permissions.py` | 5 | Backward-compatible re-export of `FilesystemPermission` |
| `libs/deepagents/deepagents/middleware/filesystem.py` | 2378 | `FilesystemPermission` dataclass (line 89), `_check_fs_permission` (line 126), filter functions (lines 139-200), per-tool enforcement (lines 943-1658) |
| `libs/deepagents/deepagents/middleware/_fs_interrupt.py` | 183 | Bridge between interrupt-mode rules and `HumanInTheLoopMiddleware`; `_build_interrupt_on_from_permissions` (line 155), predicate factories (lines 48-136) |
| `libs/deepagents/deepagents/middleware/_tool_exclusion.py` | 66 | `_ToolExclusionMiddleware` -- tail-stack companion that filters excluded tools (line 31) |
| `libs/deepagents/deepagents/graph.py` | ~867 | `create_deep_agent` -- passes `permissions` to middleware (lines 756-762), merges interrupt configs (lines 809-814), defines required middleware (lines 206-233) |
| `libs/deepagents/deepagents/backends/utils.py` | -- | `validate_path` (line 461), `_glob_anchor` (line 404), `_paths_overlap` (line 425), `to_posix_path` (line 437) |
| `libs/deepagents/deepagents/middleware/__init__.py` | -- | Public re-export of `FilesystemPermission` (line 51) |
| `libs/deepagents/deepagents/profiles/harness/harness_profiles.py` | -- | Protected scaffolding validation that prevents excluding `FilesystemMiddleware` (lines 74-79) |
