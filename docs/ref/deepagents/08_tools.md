# Tools System

This document provides exhaustive, implementation-level documentation for the tools system in the Deep Agents library. It covers how tools are passed to `create_deep_agent()`, the built-in tool suite provided by middleware, custom tool integration via the LangChain tool interface, MCP server tools, tool description overrides, tool exclusion via `_ToolExclusionMiddleware` and harness profiles, tool naming conventions, and how tools are registered on the agent graph.

---

## 1. How Tools Are Passed to create_deep_agent()

### The `tools` Parameter

The `tools` parameter on `create_deep_agent()` accepts three forms of tool definitions:

```python
# libs/deepagents/deepagents/graph.py, line 238
def create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    ...
) -> CompiledStateGraph:
```

The three accepted tool forms are:

| Tool Form | Description | Example |
|---|---|---|
| `BaseTool` instance | Canonical LangChain tool type (Pydantic model) | `StructuredTool.from_function(func=my_fn, name="my_tool", description="...")` |
| `Callable` | A plain Python function, optionally decorated with `@tool` | `@tool def search(query: str) -> str: ...` |
| `dict[str, Any]` | Lightweight dictionary tool definition | `{"name": "my_tool", "description": "...", "function": fn}` |

### Additive Semantics

User-supplied tools are **additive** -- they are merged with the built-in tool suite, never replacing it. From the docstring:

```python
# graph.py docstring excerpt
"""
tools: Additional tools the agent should have access to.

    These are merged with the built-in tool suite listed above
    (filesystem tools, `execute`, and `task`).

    Passing tools here is additive -- it never removes a built-in.
    To drop a built-in tool, register a
    `HarnessProfile` with `excluded_tools`.
"""
```

> Note: `write_todos` is **not** a default built-in. The todo tool ships
> with LangChain's `TodoListMiddleware`, which the SDK does not add to the
> default stack — only specific harness profiles opt into it.

### None Input Handling

When `tools=None` (the default), the agent is created with only the built-in tools provided by middleware. The `_apply_tool_description_overrides` function returns `None` in this case, and the agent receives no user-supplied tools:

```python
# libs/deepagents/deepagents/_tools.py, lines 46-47
if tools is None:
    return None
```

### Basic Usage

```python
from langchain_core.tools import StructuredTool
from langchain_anthropic import ChatAnthropic

def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

search_tool = StructuredTool.from_function(
    func=search_web,
    name="search_web",
    description="Search the web for information.",
)

agent = create_deep_agent(
    model=ChatAnthropic(model_name="claude-sonnet-4-6"),
    tools=[search_tool],
)
```

---

## 2. Built-in Tools (Filesystem Operations from Backends)

Deep Agents provides a suite of built-in tools injected by middleware during agent assembly. These are not part of the `tools` parameter but are added dynamically by the middleware stack.

### Default Built-in Tools

From the `create_deep_agent` docstring:

```
By default, this agent has access to the following tools:

- `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `delete`: file operations
- `execute`: run shell commands
- `task`: call subagents
```

> `write_todos` is **not** a default built-in — it ships with LangChain's
> `TodoListMiddleware`, which the SDK adds only in specific harness profiles.

### Filesystem Tools (from FilesystemMiddleware)

The `FilesystemMiddleware` class creates its filesystem tools in its `__init__` method
(seven file operations plus `execute`):

```python
# libs/deepagents/deepagents/middleware/filesystem.py
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

Each tool is created via `StructuredTool.from_function()` with both sync and async implementations, an `args_schema`, and a description drawn either from a custom override or from a default constant.

#### Tool Details

| Tool Name | Operation Type | Default Description Constant | Purpose |
|---|---|---|---|
| `ls` | `read` | `LIST_FILES_TOOL_DESCRIPTION` | Lists all files in a directory |
| `read_file` | `read` | `READ_FILE_TOOL_DESCRIPTION` | Reads a file from the filesystem with pagination |
| `write_file` | `write` | `WRITE_FILE_TOOL_DESCRIPTION` | Writes to a new file in the filesystem |
| `edit_file` | `write` | `EDIT_FILE_TOOL_DESCRIPTION` | Performs exact string replacements in files |
| `glob` | `read` | `GLOB_TOOL_DESCRIPTION` | Find files matching a glob pattern |
| `grep` | `read` | `GREP_TOOL_DESCRIPTION` | Search for a text pattern across files |
| `delete` | `write` | `DELETE_TOOL_DESCRIPTION` | Deletes a file from the filesystem |
| `execute` | N/A | `EXECUTE_TOOL_DESCRIPTION` | Executes a shell command in a sandbox |

The `execute` tool is only functional when the backend implements `SandboxBackendProtocol`. For non-sandbox backends, it returns an error message.

#### Filesystem Operation Classification

Each filesystem tool is classified as either `read` or `write` for permission enforcement:

```python
# libs/deepagents/deepagents/middleware/filesystem.py, lines 79-86
_DEFAULT_FS_TOOL_OPS: dict[str, FilesystemOperation] = {
    "ls": "read",
    "read_file": "read",
    "glob": "read",
    "grep": "read",
    "write_file": "write",
    "edit_file": "write",
}
```

#### Tool Description Example

Each tool has a rich default description. For example, the `ls` tool:

```python
# libs/deepagents/deepagents/middleware/filesystem.py, lines 404-407
LIST_FILES_TOOL_DESCRIPTION = """Lists all files in a directory.

This is useful for exploring the filesystem and finding the right file to read or edit.
You should almost ALWAYS use this tool before using the read_file or edit_file tools."""
```

#### Description Override in FilesystemMiddleware

Each tool creation method checks for a custom description before falling back to the default:

```python
# libs/deepagents/deepagents/middleware/filesystem.py, line 945
tool_description = self._custom_tool_descriptions.get("ls") or LIST_FILES_TOOL_DESCRIPTION
```

### TodoListMiddleware Tool (opt-in, not default)

The `write_todos` tool is injected by LangChain's `TodoListMiddleware` (from
`langchain.agents.middleware`). **It is not part of the default Deep Agents
stack** — `graph.py` never adds it. It appears only when a `HarnessProfile`
opts into it (via `extra_middleware`), so agents using such a profile get
`write_todos`, and profiles may also exclude it. The default stack begins with
`FilesystemMiddleware` (optionally preceded by `SkillsMiddleware`).

### Task Tool (from SubAgentMiddleware)

The `task` tool is injected by `SubAgentMiddleware` and allows the main agent to delegate work to subagents. It is only present when there are inline (synchronous) subagents available:

```python
# graph.py, lines 764-776
if inline_subagents:
    sub_agent_middleware = SubAgentMiddleware(
        backend=backend,
        subagents=inline_subagents,
        task_description=_profile.tool_description_overrides.get("task"),
        state_schema=state_schema,
    )
    deepagent_middleware.append(sub_agent_middleware)
```

### Async Subagent Tools (from AsyncSubAgentMiddleware)

When async subagents are provided, the `AsyncSubAgentMiddleware` injects tools for launching, checking, updating, cancelling, and listing background tasks:

```python
# graph.py, lines 784-788
if async_subagents:
    deepagent_middleware.append(
        AsyncSubAgentMiddleware(async_subagents=async_subagents)
    )
```

### Skills Tools (from SkillsMiddleware)

When skill source paths are provided, the `SkillsMiddleware` injects skill-based tools:

```python
# graph.py, lines 754-755
if skills is not None:
    deepagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
```

---

## 3. Custom Tools via LangChain Tool Interface

Custom tools are passed through the `tools` parameter and support the three forms described in Section 1. Here is how each form works in detail.

### BaseTool Instances

The canonical way to define custom tools. These are Pydantic models with structured `name`, `description`, and `args_schema` fields:

```python
from langchain_core.tools import BaseTool, StructuredTool

# Via StructuredTool.from_function
def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))

calc_tool = StructuredTool.from_function(
    func=calculate,
    name="calculate",
    description="Evaluate a mathematical expression.",
)

agent = create_deep_agent(
    model=ChatAnthropic(model_name="claude-sonnet-4-6"),
    tools=[calc_tool],
)
```

`BaseTool` instances support:
- Description overrides via `model_copy(update={"description": override})`
- Name extraction via `getattr(tool, "name", None)`
- Tool exclusion via name matching

### Dict Tools

Lightweight tool definitions used in HTTP-driven and JSON-configured graphs:

```python
my_tool = {
    "name": "my_tool",
    "description": "Does something useful.",
    "function": my_function,
}

agent = create_deep_agent(
    model=ChatAnthropic(model_name="claude-sonnet-4-6"),
    tools=[my_tool],
)
```

Dict tools support:
- Description overrides via shallow dict copy with updated `"description"` key
- Name extraction via `tool.get("name")`
- Tool exclusion via name matching

### Plain Callables

Functions decorated with metadata. These have limited support for description overrides:

```python
from langchain_core.tools import tool

@tool
def search(query: str) -> str:
    """Search for information."""
    return f"Results for {query}"

agent = create_deep_agent(
    model=ChatAnthropic(model_name="claude-sonnet-4-6"),
    tools=[search],
)
```

Plain callables:
- Are **left unchanged** by `_apply_tool_description_overrides` even when an override matches their name
- Support name extraction only if they have a `name` attribute (set by decorators like `@tool`)
- Support tool exclusion via name matching

### Providing Both Sync and Async Implementations

Supply a `coroutine` parameter to `StructuredTool.from_function` for the async path:

```python
def sync_fetch(url: str) -> str:
    return requests.get(url).text

async def async_fetch(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

fetch_tool = StructuredTool.from_function(
    func=sync_fetch, coroutine=async_fetch,
    name="fetch", description="Fetch content from a URL.",
)
```

### Subagent Tool Inheritance

Subagents inherit the parent agent's tools unless they declare their own:

```python
# graph.py, lines 670-675
raw_subagent_tools = spec.get("tools") if "tools" in spec else tools
subagent_tools = _apply_tool_description_overrides(
    raw_subagent_tools,
    _subagent_profile.tool_description_overrides,
)
```

Key behaviors:
- If a subagent spec contains `"tools"`, those tools are used (complete override of the parent's).
- If a subagent spec does not contain `"tools"`, the parent's original (unmodified) `tools` are inherited.
- In both cases, the subagent's own profile description overrides are applied fresh from the raw tools, preventing double-overriding.

---

## 4. MCP Server Tools

Deep Agents integrates with the broader LangChain ecosystem for tool provisioning. While the core `deepagents` library does not contain its own MCP (Model Context Protocol) server client, MCP tools can be used with Deep Agents through the LangChain tool interface.

MCP tools are external tools exposed by MCP-compatible servers. When converted to LangChain `BaseTool` instances (via LangChain's MCP integration utilities), they can be passed directly to `create_deep_agent()` through the `tools` parameter:

```python
# Conceptual example -- MCP tools as BaseTool instances
from langchain_mcp import MCPToolkit

toolkit = MCPToolkit(server_url="http://localhost:8080")
mcp_tools = toolkit.get_tools()  # Returns list[BaseTool]

agent = create_deep_agent(
    model=ChatAnthropic(model_name="claude-sonnet-4-6"),
    tools=mcp_tools,
)
```

Because MCP tools are surfaced as standard `BaseTool` instances, they participate fully in:
- Tool description overrides (via `model_copy`)
- Tool exclusion (via `_ToolExclusionMiddleware`)
- Name extraction (via `getattr(tool, "name", None)`)

The ACP (Agent Communication Protocol) server feature in Deep Agents (`deepagents.acp_server`) allows Deep Agents itself to be exposed as an MCP-compatible server, but that is the reverse direction -- making the agent's capabilities available to external consumers.

---

## 5. Tool Description Overrides Mechanism

### Overview

Tool description overrides allow harness profiles to rewrite tool descriptions per model, customizing the instructions the LLM sees for each tool without changing the tool's implementation.

### The _tool_name() Helper

```python
# libs/deepagents/deepagents/_tools.py, lines 13-27
def _tool_name(tool: BaseTool | Callable | dict[str, Any]) -> str | None:
    """Extract the tool name from any supported tool type.

    Args:
        tool: A tool in any of the forms accepted by `create_deep_agent`.

    Returns:
        The tool name, or `None` if it cannot be determined.
    """
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None
```

This function defensively extracts tool names with explicit `isinstance(name, str)` checks, guarding against:
- Dict tools with `"name": 123` or `"name": None`
- Callables with a `name` attribute that is not a string

### The _apply_tool_description_overrides() Function

```python
# libs/deepagents/deepagents/_tools.py, lines 29-65
def _apply_tool_description_overrides(
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None,
    overrides: Mapping[str, str],
) -> list[BaseTool | Callable | dict[str, Any]] | None:
    """Apply description overrides without mutating caller-owned tools.

    Only dict tools and `BaseTool` instances are rewritten. Plain callables are
    returned unchanged because safely replacing their descriptions would require
    wrapping them in new tool objects.
    """
    if tools is None:
        return None

    copied_tools: list[BaseTool | Callable | dict[str, Any]] = []
    for tool in tools:
        name = _tool_name(tool)
        override = overrides.get(name) if name is not None else None
        if override is None:
            copied_tools.append(tool)
            continue
        if isinstance(tool, dict):
            rewritten_tool = cast("dict[str, Any]", tool).copy()
            rewritten_tool["description"] = override
            copied_tools.append(rewritten_tool)
            continue
        if isinstance(tool, BaseTool):
            copied_tools.append(tool.model_copy(update={"description": override}))
            continue
        copied_tools.append(tool)
    return copied_tools
```

### Processing by Tool Type

| Tool Type | Override Mechanism | Original Mutated? |
|---|---|---|
| `dict` | Shallow `.copy()` of dict, then set `"description"` key | No |
| `BaseTool` | `model_copy(update={"description": override})` (Pydantic v2) | No |
| `Callable` | Skipped -- appended unchanged | N/A |

### Immutability Guarantee

The function never mutates caller-owned tools. This is critical because the same tool objects are shared across multiple agent/subagent configurations:

```
create_deep_agent(tools=[grep_tool, edit_tool, ...])
    |
    +-- Main agent: _apply_tool_description_overrides(tools, main_profile.overrides)
    +-- Subagent A: _apply_tool_description_overrides(tools, subagent_profile_A.overrides)
    +-- General-purpose subagent: _apply_tool_description_overrides(tools, gp_profile.overrides)
```

Without copy-on-write semantics, the last override would win for all agents.

### Where Overrides Are Applied in graph.py

Overrides are applied at five points in `create_deep_agent()`:

1. **Main agent user tools** (line 586):
   ```python
   _tools = _apply_tool_description_overrides(
       tools,
       _profile.tool_description_overrides,
   )
   ```

2. **Main agent FilesystemMiddleware** (line 756-760):
   ```python
   FilesystemMiddleware(
       backend=backend,
       custom_tool_descriptions=_profile.tool_description_overrides,
       _permissions=permissions,
   )
   ```

3. **Subagent FilesystemMiddleware** (line 623):
   ```python
   FilesystemMiddleware(
       backend=backend,
       custom_tool_descriptions=_subagent_profile.tool_description_overrides,
       _permissions=subagent_permissions,
   )
   ```

4. **Subagent user tools** (lines 671-675):
   ```python
   raw_subagent_tools = spec.get("tools") if "tools" in spec else tools
   subagent_tools = _apply_tool_description_overrides(
       raw_subagent_tools,
       _subagent_profile.tool_description_overrides,
   )
   ```

5. **Task tool description** (line 773):
   ```python
   SubAgentMiddleware(
       ...
       task_description=_profile.tool_description_overrides.get("task"),
       ...
   )
   ```

The `task` tool gets special treatment: its description override is passed directly to `SubAgentMiddleware` rather than through `_apply_tool_description_overrides`, because the task tool is created by the middleware itself.

### Override Source: HarnessProfile

Description overrides originate from harness profiles:

```python
# libs/deepagents/deepagents/profiles/harness/harness_profiles.py, lines 583-614
tool_description_overrides: Mapping[str, str] = field(default_factory=dict)
"""Per-tool description replacements keyed by tool name.

Applied only where Deep Agents has a stable description hook: built-in
filesystem tools, the `task` tool, and user-supplied `BaseTool` or dict
tools. Plain callable tools are left unchanged.
"""
```

Profiles are frozen: `tool_description_overrides` is converted to `MappingProxyType` (read-only dict) in `__post_init__`:

```python
# harness_profiles.py, lines 751-756
def __post_init__(self) -> None:
    if not isinstance(self.tool_description_overrides, MappingProxyType):
        object.__setattr__(
            self,
            "tool_description_overrides",
            MappingProxyType(dict(self.tool_description_overrides)),
        )
```

### Profile Merging of Overrides

When profiles are merged (e.g., provider-level + model-level), overrides are merged with the override profile winning per key:

```python
# harness_profiles.py, lines 1236-1239
tool_description_overrides={
    **base.tool_description_overrides,
    **override.tool_description_overrides,
}
```

### Test Coverage

```python
# libs/deepagents/tests/unit_tests/test_graph.py, lines 180-218
class TestToolDescriptionOverrides:
    def test_description_override_on_dict_copies_without_mutation(self) -> None:
        tool: dict[str, Any] = {"name": "my_tool", "description": "old"}
        result = _apply_tool_description_overrides([tool], {"my_tool": "new desc"})
        assert result is not None
        assert result[0]["description"] == "new desc"
        assert result[0] is not tool
        assert tool["description"] == "old"

    def test_description_override_on_basetool_copies_without_mutation(self) -> None:
        tool = StructuredTool.from_function(
            func=sample_tool, name="my_tool", description="old",
        )
        result = _apply_tool_description_overrides([tool], {"my_tool": "new desc"})
        assert result is not None
        rewritten = result[0]
        assert isinstance(rewritten, BaseTool)
        assert rewritten.description == "new desc"
        assert rewritten is not tool
        assert tool.description == "old"

    def test_plain_callable_is_left_unchanged(self) -> None:
        my_func.name = "my_tool"
        result = _apply_tool_description_overrides([my_func], {"my_tool": "new desc"})
        assert result == [my_func]
```

---

## 6. Tool Exclusion via _ToolExclusionMiddleware and Profiles

### Overview

Tool exclusion removes specific tools from the agent's visible tool set. Unlike description overrides (which rewrite what the model sees), exclusion completely hides tools from the model -- the model cannot call them and does not know they exist.

### _ToolExclusionMiddleware

The middleware intercepts model requests and filters out excluded tools before they reach the LLM:

```python
# libs/deepagents/deepagents/middleware/_tool_exclusion.py
class _ToolExclusionMiddleware(AgentMiddleware[Any, Any, Any]):
    """Middleware that filters excluded tools from the model request.

    Should be placed late in the middleware stack (after all
    tool-injecting middleware) so it can strip middleware-injected tools
    (filesystem, subagent, etc.) that the harness profile marks as excluded.
    """

    def __init__(self, *, excluded: frozenset[str]) -> None:
        self._excluded = excluded

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        """Filter excluded tools before they reach the model."""
        if self._excluded:
            filtered = [t for t in request.tools if _tool_name(t) not in self._excluded]
            request = request.override(tools=filtered)
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]:
        """Async variant of wrap_model_call."""
        if self._excluded:
            filtered = [t for t in request.tools if _tool_name(t) not in self._excluded]
            request = request.override(tools=filtered)
        return await handler(request)
```

### Key Design: Late Placement in the Middleware Stack

The `_ToolExclusionMiddleware` is deliberately placed **late** in the middleware stack, after all tool-injecting middleware. This ensures it can remove both:
- User-supplied tools (from the `tools` parameter)
- Middleware-injected tools (from `FilesystemMiddleware`, `SubAgentMiddleware`, etc.)

From graph.py (lines 795-796):

```python
if _profile.excluded_tools:
    deepagent_middleware.append(_ToolExclusionMiddleware(excluded=_profile.excluded_tools))
```

### Key Design: User Tools Are NOT Pre-Filtered

User-supplied tools are passed through to `create_agent` unfiltered. The exclusion middleware handles filtering at call time, not at assembly time. This is verified by tests:

```python
# libs/deepagents/tests/unit_tests/test_graph.py, lines 595-637
class TestToolExclusionWiring:
    def test_user_tools_pass_through_to_middleware_for_exclusion(self) -> None:
        """User tools are not pre-filtered; the middleware handles exclusion."""
        # ...
        user_tool_keep = {"name": "keeper", "description": "keep me"}
        user_tool_drop = {"name": "my_tool", "description": "drop me"}

        # ...
        create_deep_agent(
            model="exclprov:some-model",
            tools=[user_tool_keep, user_tool_drop],
        )

        # User tools are passed through unfiltered; middleware strips them
        passed_tools = mock_create.call_args.kwargs["tools"]
        names = [t["name"] for t in passed_tools]
        assert "keeper" in names
        assert "my_tool" in names

        # But the middleware is in the stack to handle filtering at call time
        mw_stack = mock_create.call_args.kwargs["middleware"]
        exclusion_mws = [m for m in mw_stack if isinstance(m, _ToolExclusionMiddleware)]
        assert len(exclusion_mws) == 1
        assert "my_tool" in exclusion_mws[0]._excluded
```

### _tool_name in _tool_exclusion.py

The exclusion middleware has its own `_tool_name` function, nearly identical to the one in `_tools.py` but accepting a slightly different input type:

```python
# libs/deepagents/deepagents/middleware/_tool_exclusion.py, lines 22-28
def _tool_name(tool: BaseTool | dict[str, str]) -> str | None:
    """Extract tool name from a `BaseTool` or dict tool."""
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None
```

| Function | Input Type | Used By |
|---|---|---|
| `_tools._tool_name` | `BaseTool \| Callable \| dict[str, Any]` | Description override logic |
| `_tool_exclusion._tool_name` | `BaseTool \| dict[str, str]` | Tool exclusion middleware |

The `_tools` version handles `Callable` inputs, which the exclusion middleware does not encounter because middleware-injected tools are always `BaseTool` or `dict`.

### HarnessProfile excluded_tools Field

```python
# libs/deepagents/deepagents/profiles/harness/harness_profiles.py, lines 616-627
excluded_tools: frozenset[str] = frozenset()
"""Tool names to remove from the tool set for this profile.

Applied via a tool-exclusion middleware after tool-injecting middleware
has run, so it can remove both user-supplied tools and tools added by
Deep Agents middleware from the visible tool set.

When profiles are merged, exclusions are additive rather than replacing
each other. For example, if a provider profile excludes `execute` and an
exact-model profile excludes `grep`, the resolved profile excludes both
tools.
"""
```

### Profile Merging of Excluded Tools

When profiles are merged, excluded tool sets are **unioned** (additive):

```python
# harness_profiles.py, line 1240
excluded_tools=base.excluded_tools | override.excluded_tools,
```

### Wiring in create_deep_agent

The exclusion middleware is wired into three places:

1. **Main agent** (line 795-796):
   ```python
   if _profile.excluded_tools:
       deepagent_middleware.append(_ToolExclusionMiddleware(excluded=_profile.excluded_tools))
   ```

2. **Declarative subagents** (lines 637-638):
   ```python
   if _subagent_profile.excluded_tools:
       subagent_middleware.append(_ToolExclusionMiddleware(excluded=_subagent_profile.excluded_tools))
   ```

3. **General-purpose subagent** (lines 712-713):
   ```python
   if _profile.excluded_tools:
       gp_middleware.append(_ToolExclusionMiddleware(excluded=_profile.excluded_tools))
   ```

### Usage Examples

#### Exclude the execute tool via a harness profile:

```python
from deepagents import HarnessProfile, register_harness_profile

register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfile(
        excluded_tools=frozenset({"execute"}),
    ),
)
```

#### Exclude multiple tools:

```python
register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfile(
        excluded_tools=frozenset({"execute", "write_file", "grep"}),
    ),
)
```

#### Exclude via HarnessProfileConfig (YAML/JSON-compatible):

```python
from deepagents import HarnessProfileConfig, register_harness_profile

register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfileConfig(
        excluded_tools=frozenset({"execute"}),
    ),
)
```

### TOOLS_EXCLUDED_FROM_EVICTION (Different from Tool Exclusion)

`TOOLS_EXCLUDED_FROM_EVICTION` is a distinct concept from `excluded_tools`. It controls which tools skip the large-result eviction system, not which tools are visible to the model:

| Concept | `TOOLS_EXCLUDED_FROM_EVICTION` | `excluded_tools` (profile) |
|---|---|---|
| Purpose | Skip large-result eviction | Remove tool from agent entirely |
| Effect | Tool still works, results stay in context | Tool is not available to the agent |
| Applied by | `FilesystemMiddleware.wrap_tool_call` | `_ToolExclusionMiddleware` |
| Scope | Per tool-call result | Per agent/subagent configuration |

---

## 7. Tool Naming Conventions

### Built-in Tool Names

All built-in tools follow a consistent naming convention using `snake_case`:

| Tool Name | Source Middleware | Purpose |
|---|---|---|
| `ls` | `FilesystemMiddleware` | List files in a directory |
| `read_file` | `FilesystemMiddleware` | Read a file with pagination |
| `write_file` | `FilesystemMiddleware` | Write a new file |
| `edit_file` | `FilesystemMiddleware` | Exact string replacement in files |
| `glob` | `FilesystemMiddleware` | Find files matching a glob pattern |
| `grep` | `FilesystemMiddleware` | Search for text patterns across files |
| `execute` | `FilesystemMiddleware` | Run shell commands in sandbox |
| `task` | `SubAgentMiddleware` | Delegate work to subagents |
| `write_todos` | `TodoListMiddleware` | Manage a todo list |

### Name Extraction Logic

The `_tool_name` function extracts names from any supported tool form:

```python
# libs/deepagents/deepagents/_tools.py
def _tool_name(tool: BaseTool | Callable | dict[str, Any]) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None
```

### Test Coverage for Name Extraction

```python
# libs/deepagents/tests/unit_tests/test_graph.py, lines 150-178
class TestToolName:
    """Tests for _tool_name helper."""

    def test_basetool(self) -> None:
        tool = MagicMock(spec=BaseTool)
        tool.name = "my_tool"
        assert _tool_name(tool) == "my_tool"

    def test_dict_tool(self) -> None:
        assert _tool_name({"name": "dict_tool", "description": "desc"}) == "dict_tool"

    def test_dict_tool_without_name(self) -> None:
        assert _tool_name({"description": "desc"}) is None

    def test_dict_tool_non_string_name(self) -> None:
        assert _tool_name({"name": 123}) is None

    def test_callable_with_name_attr(self) -> None:
        fn: Callable[..., Any] = MagicMock()
        fn.name = "callable_tool"
        assert _tool_name(fn) == "callable_tool"

    def test_callable_without_name(self) -> None:
        def my_func() -> None:
            pass
        # Plain functions have __name__ but not name
        assert _tool_name(my_func) is None
```

Key insight: plain functions have `__name__` but not `name`, so `_tool_name` returns `None` for them. Only functions with an explicitly set `name` attribute (e.g., from `@tool` decorator) are recognized.

### Naming Best Practices for Custom Tools

- Use `snake_case` for consistency with built-in tools.
- Avoid names that collide with built-in tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, `task`, `write_todos`).
- Set an explicit `name` attribute if using plain callables (otherwise description overrides and exclusion cannot target them by name).

---

## 8. How Tools Are Registered on the Agent Graph

### The Assembly Pipeline

Tools flow through a multi-stage pipeline from user input to the final compiled agent graph.

#### Stage 1: User Tools + Description Overrides

```python
# graph.py, lines 586-589
_tools = _apply_tool_description_overrides(
    tools,
    _profile.tool_description_overrides,
)
```

User-supplied tools get their descriptions rewritten per the active harness profile. The result `_tools` is a new list containing copies of rewritten tools and references to unchanged tools.

#### Stage 2: Middleware Stack Assembly

The middleware stack is built in a specific order:

```python
# graph.py (condensed) — default stack, no TodoListMiddleware
deepagent_middleware = [
    # SkillsMiddleware(...)                        # (conditional) skill tools
    FilesystemMiddleware(backend=backend, ...),    # fs tools (ls, read_file, ..., delete)
    SubAgentMiddleware(backend=backend, ...),      # (conditional) task tool
    create_summarization_middleware(model, ...),   # summarization
    PatchToolCallsMiddleware(),                    # dangling tool call patches
    # AsyncSubAgentMiddleware(...)                 # (conditional) async subagent tools
    # *profile.extra_middleware*                   # harness profile middleware
    AnthropicPromptCachingMiddleware(...),         # prompt caching (unconditional)
    # MemoryMiddleware(...)                        # (conditional) memory
    # HumanInTheLoopMiddleware(...)                # (conditional) HITL
]
# Then: excluded-middleware filtering; user `middleware=` spliced ahead of the
# profile/prompt-caching/memory tail; `_ToolExclusionMiddleware` appended last.
```

#### Stage 3: Final Agent Creation

```python
# graph.py, lines 844-857
return create_agent(
    model,
    system_prompt=final_system_prompt,
    tools=_tools,
    middleware=deepagent_middleware,
    response_format=response_format,
    ...
    state_schema=state_schema if state_schema is not None else DeepAgentState,
).with_config(
    {
        "recursion_limit": 9_999,
        "metadata": {
            "ls_integration": "deepagents",
            "lc_versions": {"deepagents": __version__},
            "lc_agent_name": name,
        },
    }
)
```

The `create_agent` function (from `langchain.agents`) receives both the user-supplied tools and the middleware stack. At runtime, the middleware adds its own tools to each model request. The middleware's `wrap_model_call` / `awrap_model_call` hooks modify the `ModelRequest.tools` list before the model sees it.

### PatchToolCallsMiddleware

An important utility middleware that handles dangling tool calls in conversation history. When a tool call was not completed (e.g., the conversation was interrupted), this middleware patches the message history with synthetic `ToolMessage` responses:

```python
# libs/deepagents/deepagents/middleware/patch_tool_calls.py
class PatchToolCallsMiddleware(AgentMiddleware):
    """Middleware to patch dangling tool calls in the messages history."""

    def before_agent(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:
        """Before the agent runs, handle dangling tool calls from any AIMessage."""
        messages = state["messages"]
        if not messages:
            return None

        answered_ids = {msg.tool_call_id for msg in messages if msg.type == "tool"}

        # Check if any tool calls lack matching ToolMessage responses
        # If so, inject synthetic ToolMessage responses
```

This ensures that the agent graph never encounters an AIMessage with unanswered tool calls, which would cause errors in the model call.

### Tool Flow Diagram

```
User tools -------> _apply_tool_description_overrides (main profile)
                         |
                         v
                    _tools (overridden copies)
                         |
                         v
                    create_agent(tools=_tools, middleware=[...])
                         |
                         +-- TodoListMiddleware adds write_todos
                         +-- SkillsMiddleware adds skill tools (if skills configured)
                         +-- FilesystemMiddleware adds ls, read_file, write_file,
                         |   edit_file, glob, grep, execute
                         +-- SubAgentMiddleware adds task tool (if subagents exist)
                         +-- AsyncSubAgentMiddleware adds async tools (if configured)
                         +-- _ToolExclusionMiddleware removes excluded tools
                         |
                         v
                    Final tool set visible to the LLM

User tools -------> (inherited by subagent if no "tools" in spec)
                         |
                         v
                    _apply_tool_description_overrides (subagent profile)
                         |
                         v
                    subagent_tools (subagent-specific overrides)
                         |
                         v
                    Subagent middleware stack adds its own tools
                         |
                         v
                    Final tool set for subagent
```

### Required Middleware (Cannot Be Excluded)

Certain middleware classes are protected from removal via `excluded_middleware` because they back core tool features:

```python
# graph.py, lines 206-221
_REQUIRED_MIDDLEWARE: tuple[tuple[type[AgentMiddleware], tuple[str, ...]], ...] = (
    (FilesystemMiddleware, ()),
    (SubAgentMiddleware, ()),
)
```

Attempting to exclude `FilesystemMiddleware` or `SubAgentMiddleware` via a harness profile raises `ValueError`. To remove the `task` tool specifically, use `GeneralPurposeSubagentProfile(enabled=False)` on the harness profile and pass no synchronous subagents.

---

## 9. Tool Execution Pipeline

### Execution Flow

```
  Model Response (with tool_calls)
         |
         v
  +-----------------------+
  | Tool Node (LangGraph) |
  +-----------------------+
         |
         v  For each tool_call:
  +-----------------------+
  | Middleware Stack       |
  | (wrap_tool_call hooks) |
  +-----------------------+
         |
         v
  +-----------------------+
  | Tool Function          |
  | (sync or async)        |
  +-----------------------+
         |
         v
  ToolMessage or Command
         |
         v
  Result added to state.messages
```

### The `wrap_tool_call` Hook

Middleware classes can implement `wrap_tool_call` (sync) and `awrap_tool_call` (async) to intercept tool execution. The middleware receives a `ToolCallRequest` and a `handler` callable. It can modify the request, inspect or transform the result, or short-circuit execution entirely.

The `FilesystemMiddleware` uses this hook to evict large results:

```python
def wrap_tool_call(self, request, handler):
    tool_result = handler(request)
    if (self._tool_token_limit_before_evict is None
            or request.tool_call["name"] in TOOLS_EXCLUDED_FROM_EVICTION):
        return tool_result
    return self._intercept_large_tool_result(tool_result, request.runtime)
```

### Tool Return Types

- **`ToolMessage`**: Standard message with string content, `name`, `tool_call_id`, and `status`.
- **`Command`**: A LangGraph `Command` carrying state updates alongside the tool result. Used by the `task` tool.

---

## 10. Tool Permissions

The permission system controls which filesystem operations the agent may perform, on which paths, and whether human approval is required.

### `FilesystemPermission` Dataclass

```python
from deepagents.middleware.filesystem import FilesystemPermission

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    permissions=[
        FilesystemPermission(operations=["read", "write"], paths=["/workspace/**"], mode="allow"),
        FilesystemPermission(operations=["read", "write"], paths=["/secrets/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/config/**"], mode="interrupt"),
    ],
)
```

| Field        | Type                              | Description                                           |
|--------------|-----------------------------------|-------------------------------------------------------|
| `operations` | `list[FilesystemOperation]`       | `"read"`, `"write"`, or both.                         |
| `paths`      | `list[str]`                       | Glob patterns starting with `/`. No `..` or `~`.      |
| `mode`       | `"allow"` / `"deny"` / `"interrupt"` | Effect when a tool call matches this rule.            |

### Permission Modes

- **`"allow"` (default)**: The tool call proceeds normally.
- **`"deny"`**: The tool returns a permission-denied error.
- **`"interrupt"`**: The call is paused for human approval via `HumanInTheLoopMiddleware`. The human can approve, edit, reject, or respond.

### Evaluation Order

Permissions are evaluated **in declaration order** by `_check_fs_permission`. The first rule whose operation and path pattern match determines the outcome. If no rule matches, the default is `"allow"`.

---

## 11. ToolRuntime -- Injected Runtime Context

Every built-in tool function receives a `ToolRuntime` parameter providing access to runtime context. This is the primary mechanism for tools to interact with agent state, configuration, and the backend.

### Available Attributes

| Attribute       | Type               | Description                                              |
|-----------------|--------------------|----------------------------------------------------------|
| `state`         | `FilesystemState`  | Current agent state (read-only snapshot).                 |
| `config`        | `RunnableConfig`   | LangGraph configuration for the current run.              |
| `tool_call_id`  | `str`              | Unique identifier for this tool call.                    |
| `store`         | `BaseStore | None` | Optional persistent store, if configured.                |
| `stream_writer` | `StreamWriter`     | For streaming partial results back to the caller.        |

The `ToolRuntime` parameter is automatically detected and injected by the framework. It is hidden from the LLM's view of the tool schema -- analogous to dependency injection.

---

## 12. Edge Cases and Error Handling

### No Tools Provided

When `tools=None`, `_apply_tool_description_overrides` returns `None`, and the agent is created with only middleware-injected tools.

### Override for Non-Existent Tool

If the overrides mapping contains a key that does not match any tool name, the override is silently ignored. No warning is emitted. This is intentional -- profiles may define overrides for tools that are conditionally present.

### Tool with No Name

If a tool has no extractable name (`_tool_name` returns `None`), no override is applied and no exclusion is possible. The tool is passed through unchanged.

### Duplicate Tool Names

If multiple tools share the same name, all of them receive the same override (each gets its own copy). Exclusion also affects all tools sharing the excluded name.

### Empty Excluded Set

When `_ToolExclusionMiddleware` is constructed with an empty `excluded` frozenset, it passes through all tools without modification:

```python
# _tool_exclusion.py, lines 50-53
def wrap_model_call(self, request, handler):
    if self._excluded:  # Empty frozenset is falsy
        filtered = [t for t in request.tools if _tool_name(t) not in self._excluded]
        request = request.override(tools=filtered)
    return handler(request)
```

### No Exclusion Middleware When No Excluded Tools

The exclusion middleware is only added to the stack when the profile has excluded tools:

```python
# graph.py, lines 795-796
if _profile.excluded_tools:
    deepagent_middleware.append(_ToolExclusionMiddleware(excluded=_profile.excluded_tools))
```

This is verified by tests:

```python
# test_graph.py, lines 566-591
class TestToolExclusionWiring:
    def test_no_exclusion_middleware_when_no_excluded_tools(self) -> None:
        # ...
        mw_stack = mock_create.call_args.kwargs["middleware"]
        exclusion_mws = [m for m in mw_stack if isinstance(m, _ToolExclusionMiddleware)]
        assert len(exclusion_mws) == 0
```

### Dangling Tool Calls

The `PatchToolCallsMiddleware` handles dangling tool calls (tool calls without matching `ToolMessage` responses). It injects synthetic responses:

```python
# libs/deepagents/deepagents/middleware/patch_tool_calls.py, lines 39-44
name = tool_call["name"] or "unknown"
if tool_call.get("type") == "invalid_tool_call":
    content = f"Tool call {name} with id {tool_call_id} could not be executed - arguments were malformed or truncated."
else:
    content = f"Tool call {name} with id {tool_call_id} was cancelled - another message came in before it could be completed."
```

---

## 13. Source File Reference

| File | Purpose |
|---|---|
| `libs/deepagents/deepagents/graph.py` | Main entry point; `create_deep_agent()` assembles the tool pipeline |
| `libs/deepagents/deepagents/_tools.py` | `_tool_name()` and `_apply_tool_description_overrides()` helpers |
| `libs/deepagents/deepagents/middleware/_tool_exclusion.py` | `_ToolExclusionMiddleware` implementation |
| `libs/deepagents/deepagents/middleware/filesystem.py` | `FilesystemMiddleware` with built-in tool definitions |
| `libs/deepagents/deepagents/middleware/patch_tool_calls.py` | `PatchToolCallsMiddleware` for dangling tool call handling |
| `libs/deepagents/deepagents/profiles/harness/harness_profiles.py` | `HarnessProfile` and `HarnessProfileConfig` with `excluded_tools` and `tool_description_overrides` |
| `libs/deepagents/tests/unit_tests/test_graph.py` | Tests for `TestToolName`, `TestToolDescriptionOverrides`, `TestToolExclusionMiddleware`, `TestToolExclusionWiring` |

---

*See also: Document 06 (Graph) for agent assembly, Document 10 (Backends) for the storage layer, Document 11 (Middleware Architecture) for the middleware pipeline.*
