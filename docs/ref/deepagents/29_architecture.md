# 29. System Architecture

A structural overview of the Deep Agents framework: component
relationships, data flow, the middleware pipeline, backend composition,
profile resolution, subagent architecture, and security boundaries.

> **Cross-references**: This document provides the architectural context
> for all other documentation. See individual docs for deep dives:
> - [01_big_picture.md](01_big_picture.md) -- High-level overview
> - [06_graph.md](06_graph.md) -- `create_deep_agent` and graph assembly
> - [07_state.md](07_state.md) -- `DeepAgentState` and `DeltaChannel`
> - [08_tools.md](08_tools.md) -- Tool registration and dispatch
> - [09_messages_reducer.md](09_messages_reducer.md) -- `_messages_delta_reducer`
> - [10_backends.md](10_backends.md) -- `BackendProtocol` implementations
> - [11_middleware_overview.md](11_middleware_overview.md) -- Middleware system
> - [12_filesystem_middleware.md](12_filesystem_middleware.md) -- `FilesystemMiddleware`
> - [13_context_management.md](13_context_management.md) -- Context window
> - [13_summarization_middleware.md](13_summarization_middleware.md) -- `SummarizationMiddleware`
> - [15_permissions_middleware.md](15_permissions_middleware.md) -- `FilesystemPermission`
> - [16_tool_exclusion_middleware.md](16_tool_exclusion_middleware.md) -- Tool/middleware exclusion
> - [17_subagents.md](17_subagents.md) -- Subagent system
> - [18_memory.md](18_memory.md) -- `MemoryMiddleware`
> - [19_rubric.md](19_rubric.md) -- `RubricMiddleware`
> - [20_profiles.md](20_profiles.md) -- Harness and provider profiles
> - [21_models.md](21_models.md) -- Model resolution
> - [22_excluded_middleware.md](22_excluded_middleware.md) -- Exclusion system
> - [23_acp_server.md](23_acp_server.md) -- Agent Communication Protocol
> - [24_cli_deploy.md](24_cli_deploy.md) -- CLI deployment
> - [25_code_agent.md](25_code_agent.md) -- Code agent specialization
> - [26_talon.md](26_talon.md) -- Talon runtime
> - [27_evals.md](27_evals.md) -- Evaluation framework
> - [28_execution_flows.md](28_execution_flows.md) -- Execution flow traces
> - [30_reimplementation_guide.md](30_reimplementation_guide.md) -- Invariants
> - For the `dcode` application architecture, see [dcode/README.md](dcode/README.md)

---

## 29.1 High-Level Component Diagram

```
+------------------------------------------------------------------+
|                       create_deep_agent()                         |
|                          (graph.py)                               |
+------------------------------------------------------------------+
     |            |              |             |            |
     v            v              v             v            v
+---------+ +-----------+ +----------+ +----------+ +-----------+
|  Model  | | Middleware | | Backend  | | Profile  | | Subagent  |
| Resolve | |   Stack   | | Protocol | |  System  | |  System   |
| _models | | (ordered  | | (ABC)    | | (harness | | (3 types) |
|  .py    | |  pipeline)| |          | |  +provdr)| |           |
+---------+ +-----------+ +----------+ +----------+ +-----------+
     |            |              |             |            |
     v            v              v             v            v
+---------+ +-----------+ +----------+ +----------+ +-----------+
| init_   | | 13+ mid-  | | Concrete | | Cascade  | | SubAgent  |
| chat_   | | dleware   | | backends:| | resolve: | | Compiled  |
| model() | | hooks:    | |  State   | | p:model  | | SubAgent  |
| (lang-  | | before_   | |  FileSys | | -> model | | Async     |
|  chain) | | agent,    | |  Local   | | -> provdr| | SubAgent  |
|         | | wrap_     | |  Shell   | | -> ""    | |           |
|         | | model_    | |  Sandbox | |          | |           |
|         | | call,     | |  Store   | |          | |           |
|         | | after_    | |  Compst  | |          | |           |
|         | | agent     | |          | |          | |           |
+---------+ +-----------+ +----------+ +----------+ +-----------+
                 |              |
                 v              v
          +-------------+ +----------+
          | create_agent | | Backend  |
          | (LangGraph)  | | Factory  |
          | compile to   | | (lazy    |
          | StateGraph   | |  init)   |
          +-------------+ +----------+
                 |
                 v
          +--------------------+
          |  CompiledStateGraph |
          |  recursion_limit=  |
          |  9999              |
          +--------------------+
```

The top-level entry point `create_deep_agent()` orchestrates five
subsystems. See [06_graph.md](06_graph.md) for the full parameter list
and assembly sequence. See [28_execution_flows.md](28_execution_flows.md)
Section 28.7 for the step-by-step creation flow.

---

## 29.2 Data Flow: Request to Response

```
                    +-------------------+
                    |    User Input     |
                    | HumanMessage(...) |
                    +-------------------+
                             |
                             v
+----------------------------------------------------------------+
|                    DeepAgentState                               |
|  messages: DeltaChannel(_messages_delta_reducer, snap=50)      |
|  files:    DeltaChannel(file_reducer, snap=50)                 |
|  todos:    list[TodoItem]                                      |
|  _private: PrivateStateAttr fields (not forwarded)             |
+----------------------------------------------------------------+
                             |
                    [before_agent hooks]
                             |
              +--------------+--------------+
              |         Agent Loop          |
              |                             |
              |  +--- wrap_model_call ---+  |
              |  |                       |  |
              |  | System Prompt:        |  |
              |  |  USER + BASE + SUFFIX |  |
              |  |                       |  |
              |  | Tools (from MW):      |  |
              |  |  fs: 7 tools          |  |
              |  |  subagent: task       |  |
              |  |  summarize: compact   |  |
              |  |  async: 5 tools       |  |
              |  |                       |  |
              |  +--- LLM Inference ---+ |  |
              |  |                     | |  |
              |  |   AIMessage         | |  |
              |  |   + tool_calls?     | |  |
              |  +---------------------+ |  |
              |           |              |  |
              |    [if tool_calls]       |  |
              |           |              |  |
              |  +--- Tool Dispatch --+  |  |
              |  | FilesystemMW      |  |  |
              |  | SubAgentMW        |  |  |
              |  | AsyncSubAgentMW   |  |  |
              |  +-------------------+  |  |
              |           |              |  |
              |  +--- Backend Call ---+  |  |
              |  | read/write/edit   |  |  |
              |  | ls/grep/glob     |  |  |
              |  | execute          |  |  |
              |  +-----------------+  |  |
              |           |            |  |
              |    ToolMessage         |  |
              |    (loop back)         |  |
              +------------------------+  |
                             |
                    [after_agent hooks]
                             |
                             v
                    +-------------------+
                    |   Final State     |
                    |   AIMessage(...)  |
                    +-------------------+
```

See [07_state.md](07_state.md) for `DeepAgentState` details,
[09_messages_reducer.md](09_messages_reducer.md) for the delta reducer, and
[28_execution_flows.md](28_execution_flows.md) for scenario-specific traces.

---

## 29.3 Middleware Stack Architecture

The middleware stack is the central orchestration mechanism. Each
middleware intercepts, transforms, or augments the agent's behavior
through three hook points.

```
          before_agent (once, stack order)
               |
               v
+------------------------------------+
| TodoListMiddleware           [1]   |  State: todos
| SkillsMiddleware             [2]   |  State: _skills_state
| FilesystemMiddleware         [3]   |  Tools: 7 file ops
| SubAgentMiddleware           [4]   |  Tools: task
| SummarizationMiddleware      [5]   |  State: _summarization_event
| PatchToolCallsMiddleware     [6]   |  Fixes: dangling tool calls
| AsyncSubAgentMiddleware      [7]   |  Tools: 5 async ops
| [user middleware]            [8+]  |  Custom behavior
| [profile middleware]         [+]   |  Model-specific behavior
| _ToolExclusionMiddleware     [N+1] |  Removes: excluded tools
| PromptCachingMiddleware      [N+2] |  Injects: cache markers
| MemoryMiddleware             [N+3] |  Injects: AGENTS.md
| HumanInTheLoopMiddleware     [N+4] |  Interrupts: on patterns
+------------------------------------+
               |
               v
          wrap_model_call (every LLM call, stack order)
               |
               v
          after_agent (once, REVERSE stack order)
```

### Hook execution order

| Hook | Order | Purpose |
|------|-------|---------|
| `before_agent` | Stack order (1..N) | One-time setup, state init |
| `wrap_model_call` | Stack order (1..N) | Request/response transform |
| `after_agent` | Reverse order (N..1) | Cleanup, finalization |

### Required middleware

`FilesystemMiddleware` and `SubAgentMiddleware` are in the
`_REQUIRED_MIDDLEWARE` tuple and cannot be excluded. Attempting to exclude
them raises `ValueError` at construction time.

### Exclusion system

After assembly, `_apply_excluded_middleware()` removes entries matching
`HarnessProfile.excluded_middleware`. Matching uses exact `type()`, not
`isinstance()`. `_verify_excluded_middleware_coverage()` then confirms
every exclusion entry matched at least one middleware, catching typos.
See [22_excluded_middleware.md](22_excluded_middleware.md).

---

## 29.4 Backend Architecture

```
              BackendProtocol (ABC)
              |  ls, read, write, edit
              |  grep, glob
              |  upload_files, download_files
              |
    +---------+-------------+----------+
    |         |             |          |
    v         v             v          v
 State     Filesystem    Store     BaseSandbox
 Backend   Backend       Backend   (ABC)
 (in-mem)  (disk)        (LG       |
                          Store)   |
              |                    |
              v                    v
         LocalShell            Concrete
         Backend               Sandboxes
         (disk + shell)        (Docker, VM)

         SandboxBackendProtocol (extends BackendProtocol)
         |  execute, aexecute
         |
    +----+--------+
    |             |
    v             v
 LocalShell    BaseSandbox
 Backend       subclasses

         CompositeBackend (routing)
         |  routes: {prefix: Backend}
         |  default: Backend
         |  longest-prefix-match routing
```

### Concrete backends

| Backend | Storage | Shell | Use case |
|---------|---------|-------|----------|
| `StateBackend` | Ephemeral (LangGraph state) | No | Testing, stateless |
| `FilesystemBackend` | Local disk | No | Read-only file access |
| `LocalShellBackend` | Local disk + shell | Yes | CLI development |
| `StoreBackend` | LangGraph `BaseStore` | No | Cloud persistence |
| `BaseSandbox` | Sandbox-internal | Yes | Production isolation |

### BackendFactory (removed)

> **Changed:** the SDK no longer defines a `BackendFactory` type.
> `create_deep_agent()` accepts a `BackendProtocol` instance or `None`. The only
> related callable is `NamespaceFactory`
> (`Callable[[Runtime], tuple[str, ...]]`) used by `StoreBackend` for namespace
> resolution — not for backend construction.

### FileFormat

`FileFormat = Literal["v1", "v2"]` controls file serialization in
`StateBackend`:
- `"v1"` (legacy): `list[str]` (one string per line).
- `"v2"` (current): plain `str` with encoding metadata.

See [10_backends.md](10_backends.md) for full protocol details.

---

## 29.5 Subagent Architecture

```
create_deep_agent(subagents=[...])
         |
         | classify each subagent spec
         |
    +----+----+----------+
    |         |          |
    v         v          v
 SubAgent  Compiled   AsyncSubAgent
 (dict)    SubAgent   (remote)
    |      (runnable)     |
    |         |          |
    v         v          v
 create_    use        route to
 sub_agent  directly   AsyncSubAgent
 ()                    Middleware
    |         |          |
    v         v          |
 inline_subagents        |
 (local, sync)           |
    |                    |
    v                    v
 SubAgentMiddleware    AsyncSubAgentMiddleware
 provides: task tool   provides: start_async_task
                                 check_async_task
                                 update_async_task
                                 cancel_async_task
                                 list_async_tasks
```

### SubAgent (declarative spec)

A `TypedDict` (line 36 in `subagents.py`) with fields: `name`,
`description`, `system_prompt`, `model`, `tools`, `middleware`,
`permissions`, `response_format`. Compiled to a runnable via
`create_sub_agent()` (line 459).

### CompiledSubAgent

Has a `runnable` field containing a pre-compiled LangGraph graph.
Used directly without recompilation. Does NOT inherit `interrupt_on`,
model, or permissions from the parent.

### AsyncSubAgent

A `TypedDict` (line 34 in `async_subagents.py`) with fields: `name`,
`description`, `graph_id`, optional `url`/`headers`. Routes to remote
Agent Protocol servers via the LangGraph SDK. `_ClientCache` (line 231)
lazily creates and caches sync/async clients keyed by `(url, headers)`.

### General-purpose subagent

Auto-added unless the profile sets `enabled=False`. Configured via
`GeneralPurposeSubagentProfile` (line 83 in `harness_profiles.py`) with
tri-state `enabled` (None/True/False), `description`, `system_prompt`.

### State forwarding

When dispatching to a subagent:
- `_EXCLUDED_STATE_KEYS` strips: `messages`, `todos`, `structured_response`.
- `PrivateStateAttr` fields are stripped.
- Remaining state (e.g., `files`) is forwarded.
- Fresh thread ID provides conversation isolation.

See [17_subagents.md](17_subagents.md) for full subagent documentation.

---

## 29.6 Profile System Architecture

```
register_harness_profile(key, profile)
register_provider_profile(key, profile)
         |
         v
+------------------+     +-------------------+
| HarnessProfile   |     | ProviderProfile   |
| (runtime config) |     | (model build)     |
+------------------+     +-------------------+
| base_system_     |     | init_kwargs       |
|   prompt         |     | init_kwargs_      |
| system_prompt_   |     |   factory         |
|   suffix         |     | pre_init          |
| tool_description_|     +-------------------+
|   overrides      |            |
| excluded_tools   |            v
| excluded_        |     resolve_model()
|   middleware     |     _models.py
| extra_middleware |
| general_purpose_ |
|   subagent       |
+------------------+
         |
         v
_harness_profile_for_model()
  cascade resolution:
  1. "provider:model" (exact)
  2. "model" (if colon in spec)
  3. "provider" (prefix)
  4. "" (global default)
  All matches merged via _merge_profiles()
```

### Merge strategies

| Field type | Strategy |
|-----------|----------|
| Scalar (`base_system_prompt`) | Later/more-specific wins |
| `frozenset` (`excluded_tools`) | Set union |
| Middleware lists (`extra_middleware`) | Type-keyed merge |
| `GeneralPurposeSubagentProfile` | Field-wise merge |

### HarnessProfileConfig

YAML/JSON-serializable subset of `HarnessProfile` with string-only
`excluded_middleware` entries (no class references). Validated at
`__post_init__` for grammar and scaffolding violations.

### Third-party plugins

Profiles registered via `importlib.metadata` entry points:
- `deepagents.provider_profiles`
- `deepagents.harness_profiles`

Bootstrap is lazy and thread-safe. Built-in profiles load first;
third-party plugins merge on top.

See [20_profiles.md](20_profiles.md) and [21_models.md](21_models.md).

---

## 29.7 System Prompt Assembly

```
+------------------+
| USER prompt      |  <-- system_prompt= parameter (caller instructions)
+------------------+
        +
       \n\n
        +
+------------------+
| BASE_AGENT_PROMPT|  <-- or HarnessProfile.base_system_prompt (CUSTOM)
+------------------+
        +
+------------------+
| SUFFIX           |  <-- HarnessProfile.system_prompt_suffix
+------------------+
        +
+------------------+
| Middleware        |  <-- MemoryMiddleware: AGENTS.md
| injections       |  <-- SkillsMiddleware: skill catalog
|                  |  <-- FilesystemMiddleware: file context
|                  |  <-- TodoListMiddleware: todo list
+------------------+
```

`USER` always leads so caller instructions take precedence. `BASE` provides
behavioral guidelines. `SUFFIX` sits closest to the conversation history
for model-tuning guidance.

If `system_prompt` is a `SystemMessage` object, content blocks are
composed rather than string-concatenated (lines 836-842 in `graph.py`).

---

## 29.8 Security Architecture

### Permission layers

```
FilesystemPermission rules
  |
  | operations: ["read"] or ["write"]
  | paths: glob patterns
  | mode: allow | deny | interrupt
  |
  v
_check_fs_permission() -- first-match-wins
  |
  +-- allow:     proceed to backend
  +-- deny:      error ToolMessage, no backend call
  +-- interrupt: pause graph, await human approval
```

Permissions are enforced at the tool level by `FilesystemMiddleware`,
not at the backend level. Direct backend usage bypasses permissions.

### Security boundaries

| Component | Isolation | Risk level |
|-----------|-----------|------------|
| `StateBackend` | In-memory, no disk | Low |
| `FilesystemBackend` | Disk access only | Medium |
| `LocalShellBackend` | Unrestricted host shell | High |
| `BaseSandbox` | Container/VM boundary | Low |

`LocalShellBackend` carries explicit security warnings: commands run with
the user's full system permissions, can read secrets, install packages,
and modify system files. Use `HumanInTheLoopMiddleware` and isolated
environments. For production, use `BaseSandbox` subclasses.

See [15_permissions_middleware.md](15_permissions_middleware.md) and [26_talon.md](26_talon.md).

---

## 29.9 Deployment Targets

| Target | Backend | Shell | Persistence | Docs |
|--------|---------|-------|-------------|------|
| CLI (dev) | `LocalShellBackend` | Yes | Disk | [24_cli_deploy.md](24_cli_deploy.md) |
| Testing | `StateBackend` | No | Ephemeral | [10_backends.md](10_backends.md) |
| Cloud | `StoreBackend` | No | `BaseStore` | [23_acp_server.md](23_acp_server.md) |
| Sandbox | `BaseSandbox` | Yes | Container | [26_talon.md](26_talon.md) |
| Composite | `CompositeBackend` | Mixed | Mixed | [10_backends.md](10_backends.md) |

---

## 29.10 Public API Surface

Exported from `deepagents/__init__.py` (45 lines):

| Symbol | Category | Docs |
|--------|----------|------|
| `create_deep_agent` | Entry point | [06_graph.md](06_graph.md) |
| `DeepAgentState` | State | [07_state.md](07_state.md) |
| `SubAgent` | Subagent | [17_subagents.md](17_subagents.md) |
| `CompiledSubAgent` | Subagent | [17_subagents.md](17_subagents.md) |
| `AsyncSubAgent` | Subagent | [17_subagents.md](17_subagents.md) |
| `SubAgentMiddleware` | Middleware | [17_subagents.md](17_subagents.md) |
| `AsyncSubAgentMiddleware` | Middleware | [17_subagents.md](17_subagents.md) |
| `FilesystemMiddleware` | Middleware | [12_filesystem_middleware.md](12_filesystem_middleware.md) |
| `FilesystemPermission` | Security | [15_permissions_middleware.md](15_permissions_middleware.md) |
| `MemoryMiddleware` | Middleware | [18_memory.md](18_memory.md) |
| `RubricMiddleware` | Middleware | [19_rubric.md](19_rubric.md) |
| `HarnessProfile` | Profile | [20_profiles.md](20_profiles.md) |
| `HarnessProfileConfig` | Profile | [20_profiles.md](20_profiles.md) |
| `ProviderProfile` | Profile | [20_profiles.md](20_profiles.md) |
| `GeneralPurposeSubagentProfile` | Profile | [20_profiles.md](20_profiles.md) |
| `register_harness_profile` | Registration | [20_profiles.md](20_profiles.md) |
| `register_provider_profile` | Registration | [21_models.md](21_models.md) |
