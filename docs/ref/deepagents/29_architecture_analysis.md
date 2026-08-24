# Architecture Analysis: Deep Agents Library (v0.6.12)

This document provides an exhaustive architectural analysis of the Deep Agents library,
covering design patterns, strengths, trade-offs, comparisons with alternative frameworks,
and guidance for future reimplementation efforts.

The library lives under `libs/deepagents/deepagents/` and is built on top of LangGraph
and LangChain. It provides a framework for creating AI agents with filesystem access,
sub-agent delegation, context summarization, memory, skills, and structured output.

---

## Table of Contents

1. [Design Patterns Used](#1-design-patterns-used)
2. [Architectural Strengths](#2-architectural-strengths)
3. [Architectural Trade-offs](#3-architectural-trade-offs)
4. [Comparison with Alternative Approaches](#4-comparison-with-alternative-approaches)
5. [What a Reimplementation Should Keep vs. Change](#5-what-a-reimplementation-should-keep-vs-change)
6. [Knowledge Verification Questions](#6-knowledge-verification-questions)

---

## 1. Design Patterns Used

This section catalogs the eight primary design patterns that shape the Deep Agents
architecture, with code-level analysis for each.

---

### 1.1 Factory Pattern: `create_deep_agent()`

**Location:** `graph.py` (lines 236-866)

`create_deep_agent()` is the single public entry point for constructing an agent.
It accepts primitives (strings, lists, configuration dicts) and resolves them
into the complex object graph needed to run a LangGraph-based agent.

| Aspect              | Detail                                                        |
|---------------------|---------------------------------------------------------------|
| Input               | Primitives: model name string, backend instance, middleware list, tools, profiles |
| Output              | `CompiledStateGraph` (opaque to caller)                       |
| Default model       | `ChatAnthropic(model_name="claude-sonnet-4-6")`               |
| Default backend     | `StateBackend()`                                              |
| Auto subagent       | Creates a general-purpose subagent unless explicitly disabled  |
| Function length     | ~630 lines in a single function                               |
| Complexity markers  | `noqa: C901, PLR0912, PLR0915` (linting suppressions)         |

**What the factory does internally:**

1. Resolves the model name to a model instance via `_models.py`.
2. Looks up provider and harness profiles via the registry.
3. Processes subagent specifications into compiled subagent runnables.
4. Assembles the middleware pipeline in a fixed order (13 positions).
5. Constructs the system prompt from base prompt, profile suffixes, and middleware contributions.
6. Calls `create_agent` from LangGraph to build the state graph.
7. Returns the compiled graph.

**Why a factory, not a builder:** The library chose a single function call over a
multi-step builder because the construction steps are interdependent. Profile lookup
influences middleware selection, which influences tool filtering, which influences
prompt construction. A builder would need to defer validation until a final `.build()`
call anyway, gaining little over the current approach. That said, the function's
length (~630 lines) pushes the limits of this pattern.

---

### 1.2 Middleware/Pipeline Pattern

**Location:** `middleware/` directory (10 middleware classes + 6 support modules)

The middleware pipeline is the central runtime extensibility mechanism. Each middleware
implements the `AgentMiddleware` interface, providing hooks that are called at
well-defined points during agent execution.

**Middleware Hooks:**

| Hook               | When Called               | Typical Use                                   |
|--------------------|---------------------------|-----------------------------------------------|
| `before_agent`     | Once per agent turn       | State initialization, context loading          |
| `after_agent`      | Once per agent turn       | State cleanup, persistence, rubric evaluation  |
| `wrap_model_call`  | Every model invocation    | Prompt injection, tool filtering, token counting |
| `wrap_tool_call`   | Every tool invocation     | Result interception, large result eviction      |
| `get_tools`        | During middleware assembly | Tool registration                              |

**Fixed Pipeline Order (13 positions):**

| Position | Middleware            | Purpose                                        |
|----------|-----------------------|------------------------------------------------|
| 1        | TodoList              | Task tracking state                            |
| 2        | Skills                | Skill discovery and invocation                 |
| 3        | Filesystem            | File read/write with permission enforcement    |
| 4        | SubAgent              | Synchronous sub-agent delegation               |
| 5        | Summarization         | Context window management via summarization    |
| 6        | PatchToolCalls        | Tool call result patching                      |
| 7        | AsyncSubAgent         | Asynchronous sub-agent delegation              |
| 8        | (user middleware)     | Caller-supplied middleware slots               |
| 9        | (profile extra)       | Middleware from harness profiles                |
| 10       | ToolExclusion         | Removes tools based on profile configuration   |
| 11       | PromptCaching         | Cache control marker injection                 |
| 12       | Memory                | AGENTS.md persistence                          |
| 13       | HITL                  | Human-in-the-loop interrupt handling           |

**Middleware exclusion mechanics:**

- `_apply_excluded_middleware()` in `_excluded_middleware.py` filters by exact type
  (`type(mw) in excluded_classes`), not by `isinstance`.
- `_REQUIRED_MIDDLEWARE` in `graph.py` protects `FilesystemMiddleware` and
  `SubAgentMiddleware` from exclusion.
- `_verify_excluded_middleware_coverage()` raises if any exclusion string matched
  nothing, catching typos in configuration.

---

### 1.3 Protocol Pattern: `BackendProtocol`

**Location:** `backends/` directory (7 implementations)

`BackendProtocol` is an abstract base class (ABC) defining 12 sync/async method pairs
that all storage backends must implement.

**Method Pairs:**

| Sync Method       | Async Method        | Purpose                         |
|--------------------|---------------------|---------------------------------|
| `ls`              | `als`               | List files/directories          |
| `read`            | `aread`             | Read file contents              |
| `write`           | `awrite`            | Write file contents             |
| `edit`            | `aedit`             | Edit file contents              |
| `grep`            | `agrep`             | Search file contents            |
| `glob`            | `aglob`             | Pattern-match file paths        |
| `upload_files`    | `aupload_files`     | Upload files to backend         |
| `download_files`  | `adownload_files`   | Download files from backend     |

**Extended Protocol:**

`SandboxBackendProtocol` extends `BackendProtocol` with:
- `execute` / `aexecute` - Shell command execution
- `id` property - Sandbox instance identifier

**Implementation Hierarchy:**

```
BackendProtocol (ABC)
  |-- StateBackend           (ephemeral, in LangGraph state)
  |-- StoreBackend           (persistent, cross-thread via BaseStore)
  |-- FilesystemBackend      (direct disk access, path security)
  |-- CompositeBackend       (path-prefix router to other backends)
  |-- ContextHubBackend      (LangSmith Hub with in-memory cache)

SandboxBackendProtocol (extends BackendProtocol)
  |-- BaseSandbox (abstract)
  |     |-- LangSmithSandbox (wraps LangSmith Sandbox SDK)
  |-- LocalShellBackend      (extends both FilesystemBackend AND SandboxBackendProtocol)
```

**Result Types:**

| Type              | Kind       | Purpose                                |
|-------------------|------------|----------------------------------------|
| `ReadResult`      | dataclass  | File read results with content          |
| `WriteResult`     | dataclass  | Write confirmation with path            |
| `EditResult`      | dataclass  | Edit confirmation with diff             |
| `LsResult`        | dataclass  | Directory listing                       |
| `GrepResult`      | dataclass  | Search matches                          |
| `GlobResult`      | dataclass  | Pattern match results                   |
| `ExecuteResponse` | dataclass  | Shell execution output                  |
| `FileInfo`        | TypedDict  | File metadata                           |
| `GrepMatch`       | TypedDict  | Individual grep match                   |
| `FileData`        | TypedDict  | File content data                       |

---

### 1.4 Registry Pattern: Profile Registries

**Location:** `profiles/` directory

Two global registries manage agent configuration profiles:

| Registry               | Type                           | Key Format                      |
|------------------------|--------------------------------|---------------------------------|
| `_PROVIDER_PROFILES`   | `dict[str, ProviderProfile]`   | `"provider"` or `"provider:model"` |
| `_HARNESS_PROFILES`    | `dict[str, HarnessProfile]`    | `"provider"` or `"provider:model"` |

**Lazy Bootstrap:**

- `_ensure_builtin_profiles_loaded()` initializes registries on first access.
- Uses `threading.Condition` for thread-safe initialization.
- Prevents redundant loading across concurrent access.

**Lookup Algorithm (two-tier):**

1. Attempt exact match on `"provider:model"` key.
2. Fall back to `"provider"` prefix key.
3. If both exist, merge the two (model-specific overrides provider-level defaults).

**Plugin Discovery:**

- Uses `importlib.metadata.entry_points()` for two groups:
  - `deepagents.provider_profiles`
  - `deepagents.harness_profiles`
- Registration is additive: new registrations merge with existing entries (never replace).
- Four-level error isolation for plugins:
  1. `entry_points()` call failure
  2. `ep.load()` failure
  3. Loaded object is not callable
  4. Registration function raises

---

### 1.5 Strategy Pattern: Interchangeable Backends

**Location:** `backends/` directory

All seven backend implementations conform to `BackendProtocol`, making them
interchangeable at the `create_deep_agent()` call site without any change to agent
logic.

| Backend             | Storage Model        | Key Characteristics                         |
|---------------------|----------------------|---------------------------------------------|
| `StateBackend`      | Ephemeral            | Files live in LangGraph state channel; lost on session end |
| `StoreBackend`      | Persistent           | Uses LangGraph `BaseStore` with namespaced keys |
| `FilesystemBackend` | Direct disk          | Path security: `virtual_mode` blocks `..`, `~`, enforces root containment |
| `LocalShellBackend` | Direct disk + shell  | Extends `FilesystemBackend` + `SandboxBackendProtocol` |
| `CompositeBackend`  | Routing layer        | Routes by path prefix to different backends; sorted by prefix length, longest first |
| `ContextHubBackend` | LangSmith Hub        | Persistent via agent repos; includes in-memory cache layer |
| `LangSmithSandbox`  | Remote sandbox       | Wraps LangSmith Sandbox SDK instance        |

**Backend construction:**

A backend is passed to `create_deep_agent(backend=...)` as a fully constructed
`BackendProtocol` instance (or `None`, defaulting to `StateBackend`). A former
`BackendFactory` deferred-construction type alias has been removed;
runtime-dependent behavior now lives inside individual backends (e.g.
`StoreBackend`'s `NamespaceFactory`).

---

### 1.6 Observer/AOP Pattern: `wrap_model_call`

**Location:** Middleware classes across `middleware/` directory

Every model invocation passes through each middleware's `wrap_model_call` hook,
enabling aspect-oriented behavior injection without modifying the model call itself.

**Capabilities available to `wrap_model_call`:**

- Modify the system prompt via `append_to_system_message`
- Filter available tools via `request.tools`
- Transform messages before they reach the model
- Count tokens for context management
- Trigger summarization when context grows too large
- Add cache control markers for prompt caching

**Related hooks and their scoping:**

| Hook              | Scope                | Example Use                                   |
|-------------------|----------------------|-----------------------------------------------|
| `wrap_model_call` | Every model call     | Prompt injection, tool filtering              |
| `wrap_tool_call`  | Every tool call      | `FilesystemMiddleware` evicts large results    |
| `before_agent`    | Once per agent turn  | State initialization                          |
| `after_agent`     | Once per agent turn  | `RubricMiddleware` uses `@hook_config(can_jump_to=["model"])` to loop back |

The `after_agent` hook on `RubricMiddleware` is notable: it uses
`@hook_config(can_jump_to=["model"])` to allow the agent to loop back to the model
node after rubric evaluation, enabling iterative refinement.

---

### 1.7 TypedDict over Dataclass for Agent Specifications

**Location:** `graph.py` and `middleware/subagent.py`

Sub-agent specifications use `TypedDict` instead of dataclasses, a deliberate
architectural choice.

**TypedDict definitions:**

| TypedDict          | Required Fields                        | Optional Fields (NotRequired)                              |
|--------------------|----------------------------------------|------------------------------------------------------------|
| `SubAgent`         | `name`, `description`, `system_prompt` | `tools`, `model`, `middleware`, `interrupt_on`, `skills`, `permissions`, `response_format` |
| `CompiledSubAgent` | `name`, `description`, `runnable`      | (none)                                                     |
| `AsyncSubAgent`    | `name`, `description`, `graph_id`      | `url`, `headers`                                           |
| `AsyncTask`        | `task_id`, `agent_name`, `thread_id`, `run_id`, `status`, `created_at`, `last_checked_at`, `last_updated_at` | (none) |

**Rationale for TypedDict over dataclass:**

- TypedDicts are transparent dicts at runtime, no class wrapper overhead.
- They work naturally with LangGraph state channels, which expect dict-like objects.
- They are inherently JSON-serializable without custom encoders.
- No `__init__` ceremony, no `__repr__` noise, no attribute access indirection.
- Type checking is available at development time via mypy/pyright without runtime cost.

---

### 1.8 Sentinel Pattern: `REMOVE_ALL_MESSAGES`

**Location:** `_messages_reducer.py` (imported from `langgraph.graph.message`)

`REMOVE_ALL_MESSAGES` is a sentinel value used to fully reset conversation context
within the LangGraph state channel.

**Behavior in `_messages_delta_reducer`:**

1. When `REMOVE_ALL_MESSAGES` appears in the write stream, the reducer:
   - Discards ALL existing messages in state.
   - Discards all writes that appeared before the sentinel in the same batch.
   - Only retains writes that come after the sentinel.
2. This enables complete context reset without requiring external state manipulation.
3. The sentinel integrates with the custom `DeltaChannel` implementation, which
   also handles message deduplication, tombstoning, and batch semantics.

**Complementary reducer features:**

- `snapshot_frequency=50` parameter controls how often full snapshots are taken
  versus incremental deltas.
- Separate `_file_data_delta_reducer` handles the files channel with similar
  delta semantics.
- The `DeltaChannel` approach achieves O(N) checkpoint growth instead of O(N^2)
  that would occur with naive full-state checkpointing.

---

## 2. Architectural Strengths

This section evaluates six key architectural strengths with references to specific
files and mechanisms.

---

### 2.1 Clean Separation of Concerns

The library enforces clear boundaries between three orthogonal axes of configuration
and behavior:

| Axis          | Mechanism         | Governed By                                  |
|---------------|-------------------|----------------------------------------------|
| Model config  | `ProviderProfile` | `profiles/` - model construction parameters  |
| Agent behavior| `HarnessProfile`  | `profiles/` - prompts, tool filtering, middleware |
| Runtime logic | Middleware        | `middleware/` - interception hooks            |
| Storage       | Backend           | `backends/` - file and state persistence     |
| User tools    | Tool definitions  | Registered at `create_deep_agent()` call site |

This separation means that changing the model provider (e.g., switching from Anthropic
to a different provider) requires only a `ProviderProfile` change. Changing agent
behavior (e.g., adding tool restrictions for a specific deployment) requires only a
`HarnessProfile` change. Neither requires modifying middleware logic or backend
implementations.

State schemas are composed dynamically: each middleware declares a `state_schema`
attribute, and `create_deep_agent()` merges them into the final graph state type.
This avoids a monolithic state class that would need to know about all middleware
at compile time.

---

### 2.2 Security by Default

Security is not opt-in; it is structurally enforced through multiple mechanisms.

**Required Middleware:**

`_REQUIRED_MIDDLEWARE` in `graph.py` lists `FilesystemMiddleware` and
`SubAgentMiddleware`. The exclusion system in `_excluded_middleware.py` refuses to
remove these, even if a profile or caller requests it. This prevents accidental
removal of security boundaries.

**Filesystem Permissions:**

- `FilesystemPermission` uses a first-match-wins rule with three modes:
  `allow`, `deny`, `interrupt`.
- Path validation in `FilesystemBackend` rejects:
  - Path traversal (`..` components)
  - Windows absolute paths (when running in virtual mode)
  - Paths outside configured `allowed_prefixes`
  - Home directory references (`~`)
- `virtual_mode` enforces strict root containment.

**Sub-agent Isolation:**

Sub-agents receive their own middleware stack and permission set. The parent agent's
permissions do not automatically propagate, preventing privilege escalation through
delegation.

---

### 2.3 Extensibility via Plugins

The plugin system uses Python's `importlib.metadata` entry_points mechanism, which is
the standard packaging ecosystem approach for plugin discovery.

**Supported Entry Point Groups:**

| Group                              | Purpose                           |
|------------------------------------|-----------------------------------|
| `deepagents.provider_profiles`     | Register model provider configs   |
| `deepagents.harness_profiles`      | Register agent behavior configs   |
| `deepagents_code.sandbox_providers`| Register sandbox implementations  |

**Error Isolation (four levels):**

A third-party plugin can fail at any of four stages, and each failure is logged but
never propagated to the caller:

1. `entry_points()` discovery fails (corrupted package metadata).
2. `ep.load()` fails (import error in plugin module).
3. Loaded object is not callable (plugin registered a non-function).
4. Registration function raises (plugin logic error).

This isolation ensures that a buggy plugin cannot prevent the agent from starting.

**Additive Registration:**

Profile registration merges with existing entries rather than replacing them. This
allows multiple plugins to contribute to the same provider's configuration without
conflict. The merge semantics (described in Section 3.5) vary by field type.

---

### 2.4 Immutability Discipline

The library enforces immutability at multiple levels to prevent subtle bugs from
shared mutable state.

**Frozen Dataclasses:**

`ProviderProfile` and `HarnessProfile` are frozen dataclasses (`@dataclass(frozen=True)`).
Any attempt to modify their fields after construction raises `FrozenInstanceError`.

**Frozen Init Kwargs:**

In `__post_init__`, `init_kwargs` is frozen to `MappingProxyType`, making it a
read-only view. This prevents middleware or tools from accidentally mutating
model construction parameters.

**Copy-on-Modify for Tools:**

`_apply_tool_description_overrides()` in `_tools.py` creates copies of tool objects
(via `model_copy` for Pydantic models or shallow copy for others) before applying
description overrides. The original tool definitions are never mutated, ensuring
that the same tool instance can be safely shared across multiple agent configurations.

**SubAgent Spec Processing:**

During `create_deep_agent()`, SubAgent specifications are processed into copies.
The original TypedDicts passed by the caller are not modified.

---

### 2.5 Null Object Pattern for Profiles

**Location:** Profile lookup in `profiles/`

`_harness_profile_for_model()` returns an empty `HarnessProfile()` when no profile
matches the requested model. This is a textbook Null Object pattern:

- Downstream code never needs to check for `None`.
- All field accesses return sensible defaults (empty strings, empty sets, empty dicts).
- No conditional branching is needed at usage sites.
- The agent works correctly with zero configuration, because the empty profile
  provides no overrides, no exclusions, and no restrictions.

This eliminates an entire class of `NoneType has no attribute` errors and simplifies
the control flow throughout `create_deep_agent()`.

---

### 2.6 Deprecation Discipline

**Location:** `_api/deprecation.py` and various public modules

The library uses a structured deprecation process rather than ad-hoc removal.

**Mechanisms:**

- `@deprecated` decorator from `langchain_core` with `since` and `removal` version
  parameters. This emits warnings at call sites with actionable migration guidance.
- `warn_deprecated()` function with proper `stacklevel` management, ensuring warnings
  point to the caller's code rather than to internal library code.
- Backward-compatible re-exports: for example, `permissions.py` re-exports
  `FilesystemPermission` from its new location, so existing imports continue to work
  while emitting deprecation warnings.

This approach respects semantic versioning and gives downstream consumers time to
migrate before breaking changes take effect.

---

## 3. Architectural Trade-offs

Every architectural decision involves trade-offs. This section documents six
significant trade-offs with specific evidence.

---

### 3.1 Tight Coupling to LangGraph

The library is deeply integrated with LangGraph at multiple levels:

| Integration Point      | LangGraph Dependency                           |
|------------------------|------------------------------------------------|
| Graph construction     | `create_agent()` from LangGraph                |
| Return type            | `CompiledStateGraph`                           |
| State channels         | `DeltaChannel` from `langgraph.channels.delta` |
| Checkpointing          | `Checkpointer` from LangGraph                 |
| Persistent storage     | `BaseStore` from LangGraph                     |
| Caching                | `BaseCache` from LangGraph                     |
| Message sentinel       | `REMOVE_ALL_MESSAGES` from `langgraph.graph.message` |

**Consequences:**

- The graph runtime cannot be swapped without rewriting core (`graph.py`,
  `_messages_reducer.py`, and all middleware that touches state channels).
- LangGraph version upgrades may require coordinated changes across the library.
- Testing requires LangGraph fixtures or mocks at the graph level.

**Mitigation:**

- The `BackendProtocol` abstraction insulates storage from LangGraph specifics.
- Middleware hooks are defined in library-owned interfaces, not LangGraph interfaces.
- The coupling is intentional: LangGraph provides battle-tested graph execution,
  checkpointing, and state management that would be expensive to reimplement.

---

### 3.2 Monolithic `graph.py`

`graph.py` is 867 lines, with `create_deep_agent()` spanning approximately 630 of
them (lines 236-866). The function carries three complexity suppression markers:

| Suppression | Meaning                         |
|-------------|----------------------------------|
| `C901`      | McCabe complexity too high       |
| `PLR0912`   | Too many branches                |
| `PLR0915`   | Too many statements              |

**Impact on maintainability:**

- The function handles model resolution, profile lookup, subagent processing,
  middleware assembly, prompt assembly, and graph creation in a single scope.
- Individual steps cannot be tested in isolation without calling the full function.
- Adding a new configuration dimension requires modifying this function.
- Code review is difficult because changes to one concern (e.g., profile lookup)
  are interleaved with unrelated concerns (e.g., middleware ordering).

**Why it persists:**

- The steps are genuinely interdependent (profile lookup affects middleware, which
  affects tools, which affects prompts).
- Extracting functions would require passing many intermediate values, potentially
  creating a "parameter object" that is just as complex.
- The function works correctly and is covered by integration tests, so the
  refactoring cost has not yet exceeded the maintenance cost.

---

### 3.3 Exact-Type Matching in Excluded Middleware

`_apply_excluded_middleware()` uses `type(mw) in excluded_classes` (exact type match)
rather than `isinstance(mw, excluded_class)`.

**Consequence:**

If a developer subclasses `SummarizationMiddleware` to customize its behavior, the
subclass will NOT be excluded when the parent class is listed in `excluded_middleware`.
The exclusion applies only to the exact type.

**Why this is intentional:**

This prevents accidental removal of specialized middleware. If a harness profile
excludes `SummarizationMiddleware`, it should not inadvertently remove a
domain-specific subclass like `CustomSummarizationMiddleware` that may have been
added for a specific purpose.

**The verification backstop:**

`_verify_excluded_middleware_coverage()` raises an error if any exclusion string
matched zero middleware instances. This catches typos and stale configuration
(e.g., excluding a middleware that was renamed). Combined with exact-type matching,
this creates a strict but safe exclusion system.

---

### 3.4 DeltaChannel Complexity

The custom `_messages_delta_reducer` is a sophisticated piece of infrastructure that
provides O(N) checkpoint growth, but at the cost of significant complexity.

**Features of the reducer:**

- Batch semantics: multiple writes in a single turn are processed together.
- `REMOVE_ALL_MESSAGES` sentinel handling (discard all prior state).
- Message deduplication by ID.
- Tombstoning for message deletion.
- `snapshot_frequency=50` parameter for controlling snapshot vs. delta tradeoff.
- Separate `_file_data_delta_reducer` for the files channel.

**Debugging difficulty:**

- Understanding channel behavior requires knowledge of LangGraph's internal
  channel mechanics.
- The interaction between snapshots, deltas, and sentinels creates edge cases that
  are hard to reason about.
- Checkpoint corruption (if it occurs) is difficult to diagnose because the reducer
  state is opaque.

**Why the complexity is justified:**

Without DeltaChannel, every checkpoint would store the full message history, leading
to O(N^2) total storage for N turns. For long-running agents with large contexts, this
becomes prohibitively expensive. The DeltaChannel optimization is essential for
production viability.

---

### 3.5 Inconsistent Profile Merge Semantics

When a model-specific profile is merged with a provider-level profile, different
fields follow different merge strategies:

| Field                        | Merge Strategy                                       |
|------------------------------|------------------------------------------------------|
| `base_system_prompt`         | Override wins (replaces entirely)                    |
| `system_prompt_suffix`       | Override wins (replaces entirely)                    |
| `tool_description_overrides` | Dict merge (override wins per key)                   |
| `excluded_tools`             | Set union (both contribute)                          |
| `excluded_middleware`        | Set union (both contribute)                          |
| `extra_middleware`           | Type-based merge (same-type replaces, novel appends) |
| `general_purpose_subagent`   | Field-wise merge (individual fields override)        |

**Consequence:**

There is no single mental model for "what happens when I override a profile field."
Developers must know which merge strategy applies to each field, and incorrect
assumptions can lead to unexpected behavior.

**Examples of potential confusion:**

- Setting `excluded_tools` in a model-specific profile does not replace the
  provider-level exclusions; it adds to them (set union). A developer expecting
  replacement would be surprised to find both sets applied.
- Setting `extra_middleware` with a middleware of the same type as one in the
  provider-level profile replaces that specific middleware (same-type replaces),
  but a middleware of a new type is appended. This mixed behavior within a single
  field is particularly surprising.

---

### 3.6 Large File Sizes

Several files exceed comfortable maintainability thresholds:

| File                   | Lines | Concern                              |
|------------------------|-------|--------------------------------------|
| `filesystem.py`        | 2378  | Filesystem middleware + permissions   |
| `summarization.py`     | 1790  | Context summarization logic           |
| `server.py` (ACP)      | 1038  | Agent Communication Protocol server   |
| `graph.py`             | 867   | Agent construction and state          |

**Impact:**

- Files above ~500 lines become difficult to navigate and reason about.
- Multiple concerns within a single file increase the risk of unintended interactions.
- Code review for changes in these files requires more context loading.
- IDE features like "find usages" become noisier with more symbols per file.

**Decomposition candidates:**

- `filesystem.py` could split into permission handling, path validation, tool
  definitions, and middleware logic.
- `summarization.py` could split into strategy selection, token counting, and
  the middleware wrapper.
- `graph.py` could extract subagent processing, middleware assembly, and profile
  resolution into separate modules.

---

## 4. Comparison with Alternative Approaches

This section compares Deep Agents with three alternative frameworks to highlight
the architectural choices that distinguish it.

---

### 4.1 Deep Agents vs. Pure LangGraph

| Dimension                | Deep Agents                        | Pure LangGraph                    |
|--------------------------|------------------------------------|-----------------------------------|
| Agent construction       | `create_deep_agent()` factory      | Manual graph construction         |
| Middleware               | Automatic pipeline (13 positions)  | No built-in middleware            |
| Configuration            | Profile-driven                     | Code-level configuration          |
| Filesystem tools         | Built-in with permissions          | No built-in tools                 |
| Sub-agent delegation     | Built-in with state isolation      | Manual graph nesting              |
| Summarization            | Automatic context management       | Manual implementation             |
| Memory                   | AGENTS.md persistence              | No built-in memory                |
| Skills                   | Skill discovery and invocation     | No skill system                   |
| Tool descriptions        | Overridable via profiles           | Static tool definitions           |
| Checkpoint optimization  | DeltaChannel (O(N) growth)         | Default (O(N^2) growth)           |
| HITL                     | Integrated interrupt handling      | Manual interrupt implementation   |
| Prompt caching           | Automatic cache marker injection   | Manual cache management           |

**When to use pure LangGraph:** When you need full control over graph topology,
when the middleware pipeline does not match your execution model, or when you
are building a non-agent graph (e.g., a data processing pipeline).

**When to use Deep Agents:** When you want a production-ready agent with sensible
defaults, filesystem access, sub-agent delegation, and context management without
building these from scratch.

---

### 4.2 Deep Agents vs. AutoGen

| Dimension              | Deep Agents                           | AutoGen                              |
|------------------------|---------------------------------------|--------------------------------------|
| Agent model            | Single agent + middleware pipeline    | Multi-agent conversation             |
| Sub-agents             | Sub-agents as tools (task tool); parent orchestrates | Agents talk to each other; group chat |
| Configuration          | Profile-driven (ProviderProfile, HarnessProfile) | Agent classes with role strings     |
| State management       | LangGraph state channels              | Message passing between agents       |
| Cross-cutting concerns | Middleware hooks                      | Agent-level customization            |
| Orchestration          | Parent agent decides when to delegate | Group chat manager or round-robin    |

**Key Architectural Difference:**

Deep Agents treats sub-agents as tools: the parent agent calls a "task" tool that
invokes a sub-agent and returns its result. The parent retains full control over
when and how to delegate.

AutoGen treats agents as peers in a conversation: agents send messages to each other,
and a group chat manager (or protocol) determines turn order. This enables emergent
collaboration patterns but makes orchestration less predictable.

---

### 4.3 Deep Agents vs. CrewAI

| Dimension              | Deep Agents                          | CrewAI                               |
|------------------------|--------------------------------------|--------------------------------------|
| Agent model            | Single agent + sub-agents as tools   | Agents with roles/goals/backstory    |
| Task model             | Middleware pipeline for cross-cutting | Task/Agent/Crew composition          |
| Configuration          | Factory function + profiles          | Declarative YAML or Python classes   |
| Process types          | Parent-orchestrated delegation       | Sequential, hierarchical processes   |
| Cross-cutting concerns | Middleware with ordered hooks        | Tool and task abstractions           |
| Entry point            | Single `create_deep_agent()` factory | `Crew` + `Agent` + `Task` objects    |

**Key Architectural Difference:**

CrewAI emphasizes declarative agent definition with roles, goals, and backstory.
Agents are anthropomorphized, and their behavior emerges from these descriptions.

Deep Agents emphasizes programmatic configuration through profiles and middleware.
Agents are configured through code-level abstractions (profiles, middleware lists,
backend choices) rather than natural-language role descriptions.

---

## 5. What a Reimplementation Should Keep vs. Change

Based on the architectural analysis above, this section recommends what to preserve
and what to redesign in a future reimplementation.

---

### 5.1 What to Keep

These architectural decisions have proven their value and should be preserved.

**Profile System:**
The clean separation between `ProviderProfile` (model construction) and
`HarnessProfile` (agent behavior) prevents configuration concerns from bleeding
into each other. The two-tier lookup (provider then model-specific) with merge
is intuitive and powerful. Keep the plugin discovery via entry points.

**Middleware Pipeline Pattern:**
The composable, orderable, excludable middleware pipeline is the library's most
powerful extensibility mechanism. The hook interface (`before_agent`, `after_agent`,
`wrap_model_call`, `wrap_tool_call`, `get_tools`) covers all necessary interception
points. Keep the exclusion system with its verification backstop.

**BackendProtocol Abstraction:**
The 12-method sync/async protocol provides a clean abstraction over storage. The
strategy pattern allows swapping backends without touching agent logic. (The old
`BackendFactory` deferred-construction alias has been removed — pass a
constructed backend instance.)

**Security by Default:**
Required middleware (`_REQUIRED_MIDDLEWARE`), filesystem permissions with
first-match-wins, and path validation are non-negotiable in a production agent
framework. Keep the structural enforcement rather than relying on documentation.

**Plugin Extensibility via Entry Points:**
The four-level error isolation for plugins is robust. Additive registration prevents
conflicts. The standard `importlib.metadata` mechanism is well-understood by the
Python packaging ecosystem.

**DeltaChannel Optimization:**
O(N) checkpoint growth is essential for long-running agents. The complexity is
justified by the performance benefit. Keep the optimization, but consider
documenting its internals more thoroughly.

**Immutability Discipline:**
Frozen dataclasses, `MappingProxyType` for init kwargs, and copy-on-modify for
tools prevent an entire class of shared-state bugs. This discipline should be
maintained and possibly strengthened (e.g., using `frozenset` for set-valued fields).

**Null Object Pattern:**
Returning empty `HarnessProfile()` instead of `None` eliminates conditional
branching at every usage site. This pattern should be applied consistently.

---

### 5.2 What to Change

These areas would benefit from redesign.

**Decompose `create_deep_agent()` into Smaller Units:**
The 630-line function should be broken into focused functions or a class with
methods. Candidates for extraction:

| Extraction Target       | Current Location      | Proposed Module/Method              |
|-------------------------|-----------------------|-------------------------------------|
| Model resolution        | graph.py lines ~250-300 | `_models.resolve_model()`         |
| Profile lookup + merge  | graph.py lines ~300-350 | `profiles.resolve_profiles()`     |
| SubAgent processing     | graph.py lines ~350-500 | `_subagents.compile_subagents()`  |
| Middleware assembly      | graph.py lines ~500-700 | `_middleware.assemble_pipeline()` |
| Prompt construction     | graph.py lines ~700-800 | `_prompts.build_system_prompt()`  |

**Consider a Builder Pattern:**
Instead of a single factory function with many parameters, a builder would allow
step-by-step construction with validation at each step:

```
agent = (
    DeepAgentBuilder()
    .with_model("claude-sonnet-4-6")
    .with_backend(FilesystemBackend(root="/workspace"))
    .with_middleware([custom_middleware])
    .with_subagents([analyst_agent])
    .build()
)
```

**Make Middleware Ordering Explicit and Configurable:**
The current hardcoded 13-position ordering is fragile. Consider:
- Middleware dependency declaration (e.g., "SummarizationMiddleware must run after
  FilesystemMiddleware").
- Topological sorting based on declared dependencies.
- Named slots that middleware can request (e.g., "early", "tools", "late").

**Use `typing.Protocol` Instead of ABC:**
`BackendProtocol` currently uses ABC, requiring explicit inheritance. Using
`typing.Protocol` would enable structural subtyping: any class with the right
methods would satisfy the protocol, even without inheriting from `BackendProtocol`.
This is more Pythonic and enables easier testing with ad-hoc implementations.

**Unify Profile Merge Semantics:**
Document the varying merge strategies prominently, or better, unify them. One
approach: define a `MergeStrategy` enum (`REPLACE`, `UNION`, `DICT_MERGE`,
`TYPE_MERGE`) and annotate each field with its strategy, making the behavior
self-documenting.

**Reduce File Sizes:**
Target ~300-500 lines per file. Specific decomposition proposals:

| Current File          | Lines | Proposed Split                                    |
|-----------------------|-------|---------------------------------------------------|
| `filesystem.py`      | 2378  | `filesystem/permissions.py`, `filesystem/paths.py`, `filesystem/tools.py`, `filesystem/middleware.py` |
| `summarization.py`   | 1790  | `summarization/strategies.py`, `summarization/tokens.py`, `summarization/middleware.py` |
| `server.py`          | 1038  | `server/handlers.py`, `server/protocol.py`, `server/middleware.py` |

---

## 6. Knowledge Verification Questions

These questions test understanding of the Deep Agents architecture. Each question
targets a specific architectural concept covered in this document.

---

### Question 1: Factory Pattern Scope

**Q:** What does `create_deep_agent()` return, and why does the caller not need to
know about the internal construction steps?

**A:** It returns a `CompiledStateGraph`, which is opaque to the caller. The factory
encapsulates model resolution, profile lookup, middleware assembly, subagent
compilation, and graph creation. The caller provides primitives (strings, lists,
configuration dicts) and receives a ready-to-use graph. This encapsulation means
the internal steps can change (e.g., adding a new middleware position) without
breaking callers.

---

### Question 2: Middleware Ordering

**Q:** Why does middleware ordering matter, and what would go wrong if
`PromptCaching` ran before `Summarization`?

**A:** Middleware ordering matters because each `wrap_model_call` hook can modify the
messages, tools, and system prompt that subsequent middleware see. If `PromptCaching`
(position 11) ran before `Summarization` (position 5), cache control markers would be
injected into messages that might subsequently be removed or modified by
summarization. The markers would be wasted, and the cache hit rate would drop because
the cached content no longer matches what reaches the model.

---

### Question 3: Required Middleware

**Q:** What are the required middleware, and what prevents their exclusion?

**A:** `FilesystemMiddleware` and `SubAgentMiddleware` are listed in
`_REQUIRED_MIDDLEWARE` in `graph.py`. The `_apply_excluded_middleware()` function
in `_excluded_middleware.py` checks each middleware type against this list before
applying exclusions. If a profile or caller attempts to exclude a required
middleware, the exclusion is silently ignored (the middleware remains in the pipeline).

---

### Question 4: Backend Swappability

**Q:** How would you switch from ephemeral file storage to persistent disk storage
without changing any agent logic?

**A:** Replace `StateBackend()` with `FilesystemBackend(root="/workspace")` in the
`create_deep_agent()` call. Because both implement `BackendProtocol` with the same
12 method pairs, all middleware and tools that interact with the backend continue to
work without modification. The `FilesystemBackend` adds path security (traversal
prevention, root containment) that `StateBackend` does not need.

---

### Question 5: Profile Merge Behavior

**Q:** If a provider-level profile sets `excluded_tools={"tool_a"}` and a
model-specific profile sets `excluded_tools={"tool_b"}`, what tools are excluded?

**A:** Both `tool_a` and `tool_b` are excluded. The `excluded_tools` field uses set
union as its merge strategy, so contributions from both the provider-level and
model-specific profiles are combined. This is different from `base_system_prompt`,
which uses an override-wins strategy where the model-specific value would completely
replace the provider-level value.

---

### Question 6: Plugin Error Isolation

**Q:** What happens if a third-party plugin registered via
`deepagents.provider_profiles` raises an exception during its registration function?

**A:** The exception is caught and logged at the fourth level of the four-level error
isolation system. The agent continues to start normally with all other profiles
intact. The four levels protect against: (1) `entry_points()` discovery failure,
(2) `ep.load()` import failure, (3) loaded object not being callable, and
(4) registration function raising. Each level catches its specific failure and
logs it without propagating.

---

### Question 7: Exact-Type Exclusion

**Q:** If you subclass `SummarizationMiddleware` and the harness profile excludes
`SummarizationMiddleware`, is your subclass excluded?

**A:** No. The exclusion system uses exact-type matching (`type(mw) in excluded_classes`),
not `isinstance`. Your subclass has a different `type()` than `SummarizationMiddleware`,
so it will not match the exclusion. This is intentional: it prevents accidental
removal of specialized middleware subclasses. If `_verify_excluded_middleware_coverage()`
is active, excluding a type that matches nothing would raise an error, alerting you to
the mismatch.

---

### Question 8: DeltaChannel Justification

**Q:** Why does the library use a custom `DeltaChannel` instead of LangGraph's
default state channels, and what is the performance difference?

**A:** The default channel stores the full message list in every checkpoint, leading to
O(N^2) total storage over N turns (each checkpoint is O(N), and there are N of them).
The custom `DeltaChannel` stores only the delta (new messages) in each checkpoint,
achieving O(N) total storage. For a 100-turn conversation with 1000 messages, this is
the difference between ~50,000 message copies and ~1,000 message copies. The
`snapshot_frequency=50` parameter controls how often full snapshots are taken to
support efficient random-access reads.

---

### Question 9: CompositeBackend Routing

**Q:** How does `CompositeBackend` decide which backend handles a given file path?

**A:** `CompositeBackend` routes by path prefix. It maintains a mapping from path
prefixes to backend instances, sorted by prefix length (longest first). When a file
operation arrives, the backend iterates through prefixes and selects the first match.
Longest-first sorting ensures that more specific prefixes take priority: a prefix of
`/workspace/data/` would match before `/workspace/` for a path like
`/workspace/data/file.txt`.

---

### Question 10: TypedDict vs. Dataclass for SubAgent

**Q:** Why does the library use `TypedDict` instead of `dataclass` for `SubAgent`
specifications, and what would break if you switched to dataclasses?

**A:** TypedDicts are used because they are transparent dicts at runtime, which
means they: (1) work naturally with LangGraph state channels that expect dict-like
objects, (2) are inherently JSON-serializable without custom encoders, and
(3) require no `__init__` ceremony. If you switched to dataclasses, you would need to
add serialization logic for LangGraph state channels, handle `__init__` parameter
ordering, and potentially add custom JSON encoders. The state channel system would
need adapters to convert between dataclass instances and the dicts it expects.

---

## Appendix: File Reference

| File                       | Lines | Primary Pattern                    |
|----------------------------|-------|------------------------------------|
| `graph.py`                 | 867   | Factory, State definition          |
| `_messages_reducer.py`     | --    | Sentinel, DeltaChannel             |
| `_models.py`               | --    | Model resolution                   |
| `_tools.py`                | --    | Copy-on-modify for tool overrides  |
| `_excluded_middleware.py`  | --    | Exact-type exclusion + verification|
| `middleware/`              | --    | Pipeline, Observer/AOP             |
| `profiles/`               | --    | Registry, Null Object              |
| `backends/`               | --    | Protocol, Strategy                 |
| `_api/deprecation.py`     | --    | Deprecation helpers                |
| `filesystem.py`           | 2378  | Security, Permissions              |
| `summarization.py`        | 1790  | Context management                 |
| `server.py`               | 1038  | ACP protocol                       |

---

*Generated for Deep Agents v0.6.12. Based on static architecture analysis of
`libs/deepagents/deepagents/`.*
