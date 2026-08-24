# Graph Assembly: `graph.py` -- The Heart of Deep Agents

This document provides exhaustive, implementation-level coverage of
`libs/deepagents/deepagents/graph.py`, the central module of the entire
Deep Agents framework. Every agent ultimately flows through the single
factory function `create_deep_agent()`, which assembles the model, system
prompt, middleware stack, tool set, subagents, and checkpointing into a
compiled LangGraph state graph.

**Source file:** `libs/deepagents/deepagents/graph.py` (867 lines)

---

## Table of Contents

1. [Module Overview](#module-overview)
2. [Imports and Dependencies](#imports-and-dependencies)
3. [DeepAgentState](#deepagentstate)
4. [BASE_AGENT_PROMPT](#base_agent_prompt)
5. [Prompt Assembly Order](#prompt-assembly-order)
6. [_build_default_model()](#_build_default_model)
7. [get_default_model()](#get_default_model)
8. [_merge_fs_interrupt_on()](#_merge_fs_interrupt_on)
9. [Required Middleware Constants](#required-middleware-constants)
10. [create_deep_agent()](#create_deep_agent)
    - [Parameters](#parameters)
    - [Model Resolution](#model-resolution)
    - [Harness Profile Resolution](#harness-profile-resolution)
    - [Tool Description Overrides](#tool-description-overrides)
    - [Backend Initialization](#backend-initialization)
    - [Subagent Processing](#subagent-processing)
    - [General-Purpose Subagent Auto-Addition](#general-purpose-subagent-auto-addition)
    - [Main Agent Middleware Stack Assembly](#main-agent-middleware-stack-assembly)
    - [Excluded Middleware Filtering](#excluded-middleware-filtering)
    - [Private State Field Detection](#private-state-field-detection)
    - [Final System Prompt Assembly](#final-system-prompt-assembly)
    - [Graph Compilation and Return](#graph-compilation-and-return)
11. [Middleware Stack Ordering](#middleware-stack-ordering)
12. [Recursion Limit and Metadata](#recursion-limit-and-metadata)
13. [Architectural Invariants](#architectural-invariants)

---

## Module Overview

`graph.py` is the single entry point for constructing a Deep Agent. The
module's docstring summarizes it:

> Provides `create_deep_agent`, the main entry point for constructing a
> fully configured deep agent with planning, filesystem, subagent, and
> summarization middleware.

The file defines one class (`DeepAgentState`), one constant
(`BASE_AGENT_PROMPT`), several internal helpers, and the main public
function `create_deep_agent()`. Everything in the module exists to
support this one factory function.

---

## Imports and Dependencies

The module draws from five major packages, plus internal Deep Agents
modules. Understanding these imports is essential to understanding how
the graph is assembled.

### LangChain Core Imports

| Import | Source | Purpose |
|--------|--------|---------|
| `AgentState` | `langchain.agents` | Base TypedDict for agent state; `DeepAgentState` extends it. |
| `create_agent` | `langchain.agents` | The LangChain factory that compiles a state graph from model + middleware + tools. `create_deep_agent` delegates to it at the very end. |
| `HumanInTheLoopMiddleware` | `langchain.agents.middleware` | Installs interrupt-before-execution checkpoints for human approval of specific tool calls. |
| `InterruptOnConfig` | `langchain.agents.middleware` | Configuration object for per-tool interrupt rules. Supports `allowed_decisions` and `when` predicates. |
| `AgentMiddleware` | `langchain.agents.middleware.types` | Type alias for all middleware; used in type annotations throughout. |
| `InputAgentState`, `OutputAgentState`, `ResponseT` | `langchain.agents.middleware.types` | Generic types for graph input/output typing. |
| `ResponseFormat` | `langchain.agents.structured_output` | For structured output response formatting. |

### Anthropic-Specific Imports

| Import | Source | Purpose |
|--------|--------|---------|
| `ChatAnthropic` | `langchain_anthropic` | The default model class. `_build_default_model()` instantiates it with `claude-sonnet-4-6`. |
| `AnthropicPromptCachingMiddleware` | `langchain_anthropic.middleware` | Applies Anthropic prompt caching markers. Configured with `unsupported_model_behavior="ignore"` so it no-ops for non-Anthropic models. Always included in every middleware stack. |

### LangChain Core Library Imports

| Import | Source | Purpose |
|--------|--------|---------|
| `BaseChatModel` | `langchain_core.language_models` | Abstract base for all chat models. `model` parameter accepts this or a string. |
| `AnyMessage` | `langchain_core.messages` | Union type for all message types; used in `DeepAgentState.messages`. |
| `SystemMessage` | `langchain_core.messages` | For system prompt composition when the caller passes a `SystemMessage` object with `cache_control` markers. |
| `BaseTool` | `langchain_core.tools` | Type for tool objects in the `tools` parameter. |

### LangGraph Imports

| Import | Source | Purpose |
|--------|--------|---------|
| `BaseCache` | `langgraph.cache.base` | Optional cache for the compiled graph. |
| `DeltaChannel` | `langgraph.channels.delta` | The key performance optimization. Wraps the messages field to reduce checkpoint growth from O(N^2) to O(N). |
| `CompiledStateGraph` | `langgraph.graph.state` | The return type of `create_deep_agent()`. A fully compiled, executable LangGraph state machine. |
| `BaseStore` | `langgraph.store.base` | Optional persistent key-value store, required when using `StoreBackend`. |
| `Checkpointer` | `langgraph.types` | Optional checkpointer for persisting agent state between runs. |
| `ContextT` | `langgraph.typing` | Generic type for immutable run-scoped context. |

### Internal Deep Agents Imports

| Import | Source | Purpose |
|--------|--------|---------|
| `deprecated`, `warn_deprecated` | `deepagents._api.deprecation` | Deprecation decorator and warning function. |
| `_apply_excluded_middleware`, `_validate_excluded_middleware_config`, `_verify_excluded_middleware_coverage` | `deepagents._excluded_middleware` | Three-phase pipeline for harness profile middleware exclusion. |
| `_messages_delta_reducer` | `deepagents._messages_reducer` | The custom reducer function used inside `DeltaChannel` for the messages field. |
| `resolve_model` | `deepagents._models` | Resolves a string like `"openai:gpt-5.5"` into a `BaseChatModel` instance. |
| `_apply_tool_description_overrides` | `deepagents._tools` | Rewrites tool descriptions per harness profile overrides. |
| `__version__` | `deepagents._version` | Package version, included in graph metadata. |
| `StateBackend` | `deepagents.backends` | Default backend when none is provided. |
| `BackendProtocol` | `deepagents.backends.protocol` | The protocol type for pluggable backends. (There is no `BackendFactory` type; `backend` accepts a `BackendProtocol` instance or `None`.) |
| `_build_interrupt_on_from_permissions` | `deepagents.middleware._fs_interrupt` | Converts filesystem permission rules into `interrupt_on` configs. |
| `private_state_field_names` | `deepagents.middleware._state` | Identifies fields annotated with `PrivateStateAttr` across middleware state schemas. |
| `_ToolExclusionMiddleware` | `deepagents.middleware._tool_exclusion` | Filters tools by profile exclusion lists. |
| `AsyncSubAgent`, `AsyncSubAgentMiddleware` | `deepagents.middleware.async_subagents` | Remote/background subagent support. |
| `FilesystemMiddleware`, `FilesystemPermission` | `deepagents.middleware.filesystem` | Filesystem tool suite and permission rules. |
| `MemoryMiddleware` | `deepagents.middleware.memory` | Loads AGENTS.md memory files into the system prompt. |
| `PatchToolCallsMiddleware` | `deepagents.middleware.patch_tool_calls` | Patches malformed tool calls before execution. |
| `SkillsMiddleware` | `deepagents.middleware.skills` | Loads and exposes skill definitions from source paths. |
| `GENERAL_PURPOSE_SUBAGENT`, `CompiledSubAgent`, `SubAgent`, `SubAgentMiddleware` | `deepagents.middleware.subagents` | Inline subagent support: declarative specs, compiled runnables, and the middleware that routes `task` tool calls. |
| `create_summarization_middleware` | `deepagents.middleware.summarization` | Creates the context-window summarization middleware. |
| `GeneralPurposeSubagentProfile`, `_apply_profile_prompt`, `_harness_profile_for_model` | `deepagents.profiles.harness.harness_profiles` | Harness profile resolution and prompt assembly. |

---

## DeepAgentState

```python
class DeepAgentState(AgentState):
    """AgentState with DeltaChannel on messages to reduce checkpoint growth
    from O(N^2) to O(N)."""

    messages: Required[Annotated[
        list[AnyMessage],
        DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)
    ]]
```

`DeepAgentState` extends LangChain's `AgentState` TypedDict with a
single override: the `messages` field is wrapped in a `DeltaChannel`
instead of using the default `add_messages` reducer.

### Why DeltaChannel Matters

Without `DeltaChannel`, every LangGraph checkpoint stores a full copy of
the messages list. For a long conversation with N messages, this produces
O(N^2) total checkpoint storage because each of the N checkpoints stores
an increasingly large copy.

`DeltaChannel` changes this to O(N) by storing only the *delta* (new or
changed messages) at each checkpoint. On replay, the channel
reconstructs the full list by replaying the reducer over all accumulated
deltas.

### snapshot_frequency=50

The `snapshot_frequency=50` parameter means a full snapshot of the
messages list is written to the checkpoint every 50 steps, rather than
only at the beginning. This bounds the maximum replay cost: to
reconstruct state, the system only needs to start from the nearest
snapshot and replay at most 49 deltas, rather than replaying from the
very beginning of the conversation.

### The Reducer Function

The `_messages_delta_reducer` function is passed to `DeltaChannel` as
the combining function. It handles:

- Batch processing of multiple write batches per step
- Deduplication by message ID (updates in place)
- Tombstone removal via `RemoveMessage`
- Full reset via `REMOVE_ALL_MESSAGES` sentinel
- Coercion of raw dicts/strings/tuples to typed `BaseMessage` objects

See Document 09 (Messages Reducer) and Document 07 (State) for the
full reducer specification.

### TypedDict Subclass Constraint

`DeepAgentState` is a `TypedDict`. Python's `TypedDict` does not
support `issubclass()`, so the subclass constraint on the
`state_schema` parameter of `create_deep_agent()` is enforced by
typing alone, not validated at runtime. The code comments note this
explicitly.

---

## BASE_AGENT_PROMPT (deprecated)

> **Changed in 0.7.0.** `BASE_AGENT_PROMPT` is **deprecated** and was renamed
> internally to `_LEGACY_BASE_AGENT_PROMPT` (`graph.py:76`). Accessing the old
> name now raises a deprecation warning (`graph.py:123-135`). It is **no longer
> the default system prompt.** By default the base prompt is **empty**
> (`_apply_profile_prompt(_profile, "")`, `graph.py:890`) unless a
> `HarnessProfile` supplies a `base_system_prompt`. The historical content below
> is retained for reference — it now lives only inside a harness profile that
> chooses to opt into it.

The legacy `_LEGACY_BASE_AGENT_PROMPT` is a multi-line string organized into
five sections.

### Section Breakdown

**Core Behavior:**
- Be concise and direct; do not over-explain.
- Never add preamble like "Sure!", "Great question!", or "I'll now...".
- If a request is underspecified, ask only the minimum followup needed.
- If asked how to approach something, explain first, then act.

**Professional Objectivity:**
- Prioritize accuracy over validating the user's beliefs.
- Disagree respectfully when the user is incorrect.
- Avoid unnecessary superlatives, praise, or emotional validation.

**Doing Tasks:**
1. Understand first -- read relevant files, check existing patterns.
2. Act -- implement the solution.
3. Verify -- check work against what was asked, not against own output.
- Keep working until the task is fully complete.
- Only yield back to the user when the task is done or genuinely blocked.
- If something fails repeatedly, stop and analyze *why*.

**Clarifying Requests:**
- Do not ask for details already supplied.
- Use reasonable defaults when implied.
- Prioritize missing semantics (content, delivery, detail level, alert criteria).
- Ask domain-defining questions before implementation questions.
- For monitoring/alerting requests, ask about signals, thresholds, and trigger conditions.

**Progress Updates:**
- For longer tasks, provide brief progress updates at reasonable intervals.

### Design Rationale

The prompt is deliberately anti-chatbot: it instructs the model to avoid
pleasantries, avoid explaining what it will do instead of doing it, and
keep working until tasks are complete. This aligns with the "agent"
identity rather than a "chatbot" identity.

---

## Prompt Assembly Order

The final system prompt sent to the model is composed from up to four
named parts, always in this order:

1. **USER** -- the `system_prompt=` argument to `create_deep_agent()`
   (`str` or `SystemMessage`). When unset, no USER segment is included.

2. **BASE** or **CUSTOM** -- **empty by default** since 0.7.0. When a
   `HarnessProfile` provides `base_system_prompt`, it fills the BASE segment
   (via `_apply_profile_prompt`). The historical `_LEGACY_BASE_AGENT_PROMPT` is
   only inserted here by a profile that opts into it.

3. **SUFFIX** -- `HarnessProfile.system_prompt_suffix`. When set,
   appended last. When unset, no SUFFIX segment is included.

Parts are joined by blank lines (`\n\n`).

### Two Critical Invariants

1. **USER is always at the front**, so caller instructions take
   precedence over SDK and profile content regardless of which model is
   selected.

2. **SUFFIX is always at the end**, so model-tuning guidance sits
   closest to the conversation history (where the model attends most).

### SystemMessage Handling

When `system_prompt` is a `SystemMessage` (not a plain string), the
assembly preserves the message's existing `content_blocks` list and
appends the right-hand assembly (BASE + SUFFIX) as an additional text
content block. This preserves any `cache_control` markers the caller
set on the original `SystemMessage`.

The implementation:

```python
if system_prompt is None:
    final_system_prompt = base_prompt
elif isinstance(system_prompt, SystemMessage):
    final_system_prompt = SystemMessage(
        content_blocks=[
            *system_prompt.content_blocks,
            {"type": "text", "text": f"\n\n{base_prompt}"}
        ]
    )
else:
    final_system_prompt = system_prompt + "\n\n" + base_prompt
```

---

## _build_default_model()

```python
def _build_default_model() -> ChatAnthropic:
    return ChatAnthropic(model_name="claude-sonnet-4-6")
```

Internal helper that constructs the default model. This is separated
from `get_default_model()` so that the `create_deep_agent` parameter-level
`model=None` warning is not paired with a separate function-level
deprecation warning from `get_default_model`. Direct user calls to
`get_default_model()` still see its decorator warning.

The default model is `claude-sonnet-4-6`.

---

## get_default_model()

```python
@deprecated(
    since="0.5.3",
    removal="1.0.0",
    message="Relying on the default model is deprecated...",
    package="deepagents",
)
def get_default_model() -> ChatAnthropic:
    return _build_default_model()
```

Public API function, deprecated since 0.5.3 with planned removal in
1.0.0. The deprecation decorator emits a warning once per process. The
function simply delegates to `_build_default_model()`.

The deprecation message directs users to construct their model
explicitly, for example `ChatAnthropic(model_name="claude-sonnet-4-6")`.

---

## _merge_fs_interrupt_on()

```python
def _merge_fs_interrupt_on(
    fs_interrupt_on: dict[str, InterruptOnConfig],
    user_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
) -> dict[str, bool | InterruptOnConfig] | None:
```

Merges two sources of interrupt configuration:

1. **Filesystem-permission-derived configs** -- generated by
   `_build_interrupt_on_from_permissions()` from any `permissions`
   rules with `mode="interrupt"`. These use `when` predicates that
   check whether the tool call's path argument matches an
   interrupt-mode rule.

2. **User-supplied `interrupt_on`** -- passed directly to
   `create_deep_agent()`.

User-supplied entries override generated ones per tool name. The
function returns `None` when both inputs are empty, allowing callers
to skip installing `HumanInTheLoopMiddleware` entirely.

The merge strategy is simple: start with the filesystem-derived configs,
then overlay user-supplied entries:

```python
merged = {**fs_interrupt_on}
if user_interrupt_on:
    merged.update(user_interrupt_on)
return merged
```

---

## Required Middleware Constants

### _REQUIRED_MIDDLEWARE

```python
_REQUIRED_MIDDLEWARE: tuple[
    tuple[type[AgentMiddleware], tuple[str, ...]], ...
] = (
    (FilesystemMiddleware, ()),
    (SubAgentMiddleware, ()),
)
```

A tuple of pairs, where each pair is `(middleware_class,
extra_name_aliases)`. These are the scaffolding middleware that core
deep agent features depend on. They cannot be excluded by
`HarnessProfile.excluded_middleware`.

- **`FilesystemMiddleware`** backs every built-in file tool (`ls`,
  `read_file`, `write_file`, `edit_file`, `glob`, `grep`) and
  enforces `permissions` rules (a security guarantee).

- **`SubAgentMiddleware`** backs the `task` tool handler.

### _REQUIRED_MIDDLEWARE_CLASSES

```python
_REQUIRED_MIDDLEWARE_CLASSES: frozenset[type[AgentMiddleware]] = frozenset(
    cls for cls, _ in _REQUIRED_MIDDLEWARE
)
```

A frozenset of the class types extracted from `_REQUIRED_MIDDLEWARE`.
Used for quick membership testing when validating exclusions.

### _REQUIRED_MIDDLEWARE_NAMES

```python
_REQUIRED_MIDDLEWARE_NAMES: frozenset[str] = frozenset(
    name for cls, aliases in _REQUIRED_MIDDLEWARE
    for name in (cls.__name__, *aliases)
)
```

A frozenset of all `.name` values (class `__name__` plus any extra
aliases) that cannot be excluded. Used for quick membership testing
when validating string-form exclusions.

---

## create_deep_agent()

This is the main public API of the entire Deep Agents framework.
Spanning lines 236 through 866, it is the largest single function in
the codebase. It accepts 16 parameters (1 positional, 15 keyword-only)
and returns a `CompiledStateGraph`.

### Parameters

#### model: str | BaseChatModel | None = None

The language model to use. Accepts three forms:

1. **`None`** (deprecated since 0.5.3) -- falls back to
   `_build_default_model()` which returns
   `ChatAnthropic(model_name="claude-sonnet-4-6")`. Emits a
   deprecation warning.

2. **A string** -- e.g. `"openai:gpt-5.5"`. Passed through
   `resolve_model()` which delegates to LangChain's
   `init_chat_model()`.

3. **A `BaseChatModel` instance** -- used directly after passing
   through `resolve_model()` (which returns it unchanged).

The parameter type will change from `BaseChatModel | str | None` to
`BaseChatModel | str` in deepagents 1.0.0.

#### tools: Sequence[BaseTool | Callable | dict] | None = None

Additional tools the agent should have access to. These are merged
with the built-in tool suite (filesystem tools — `ls`, `read_file`,
`write_file`, `edit_file`, `delete`, `glob`, `grep` — plus `execute`
and `task`). Passing tools is additive -- it never removes a built-in
tool. To drop a built-in tool, register a `HarnessProfile`
with `excluded_tools`.

#### system_prompt: str | SystemMessage | None = None

Custom system instructions placed at the front of the system prompt.
See the [Prompt Assembly Order](#prompt-assembly-order) section above
for the full composition rules.

#### middleware: Sequence[AgentMiddleware] = ()

Additional middleware inserted between the base stack and the tail
stack. See [Middleware Stack Ordering](#middleware-stack-ordering) for
the full ordering.

#### subagents: Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None = None

Subagent specifications. Three forms are supported:

1. **`SubAgent`** -- declarative synchronous subagent spec with
   `name`, `description`, `system_prompt`, and optional overrides for
   `tools`, `model`, `middleware`, `interrupt_on`, `skills`, and
   `permissions`.

2. **`CompiledSubAgent`** -- pre-compiled runnable with a `runnable`
   field. Used as-is.

3. **`AsyncSubAgent`** -- remote/background subagent spec with
   `graph_id`, optional `url` and `headers`. Routed to
   `AsyncSubAgentMiddleware` instead of `SubAgentMiddleware`.

#### skills: list[str] | None = None

Skill source paths (POSIX format, relative to the backend root).
When provided, a `SkillsMiddleware` is added to the stack.

#### memory: list[str] | None = None

Memory file paths (AGENTS.md files). When provided, a
`MemoryMiddleware` is added to the tail stack with
`add_cache_control=True`.

#### permissions: list[FilesystemPermission] | None = None

Filesystem permission rules. Evaluated in declaration order; first
match wins. If no rule matches, the call is allowed. Modes are
`"allow"` (default), `"deny"`, and `"interrupt"`. Subagents inherit
these rules unless they specify their own `permissions` field.

#### backend: BackendProtocol | None = None

Optional backend for file storage and execution. Defaults to
`StateBackend()` when `None`.

#### interrupt_on: dict[str, bool | InterruptOnConfig] | None = None

Per-tool interrupt configurations. Applied to the main agent.
Declarative `SubAgent` specs inherit this by default (overridable per
subagent). `CompiledSubAgent` and `AsyncSubAgent` do not inherit.

#### response_format: ResponseFormat | type | dict | None = None

Structured output response format. Passed through to `create_agent`.

#### state_schema: type[DeepAgentState] | None = None

Custom state schema. Must be a TypedDict subclass of
`DeepAgentState`. When provided, used as the base graph schema and
forwarded to declarative subagent compilation. `CompiledSubAgent`
runnables do not inherit this schema.

#### context_schema: type[ContextT] | None = None

Immutable run-scoped context schema. Passed through to `create_agent`.

#### checkpointer: Checkpointer | None = None

Optional checkpointer for state persistence between runs. Passed
through to `create_agent`.

#### store: BaseStore | None = None

Optional persistent key-value store. Required when using
`StoreBackend`. Passed through to `create_agent`.

#### debug: bool = False

Debug mode flag. Passed through to `create_agent`.

#### name: str | None = None

Agent name. Passed through to `create_agent` and included in the
graph metadata.

#### cache: BaseCache | None = None

Optional cache. Passed through to `create_agent`.

### Return Type

```python
CompiledStateGraph[
    AgentState[ResponseT],
    ContextT,
    InputAgentState,
    OutputAgentState[ResponseT]
]
```

A fully compiled, executable LangGraph state machine with
`recursion_limit=9999` and metadata including the Deep Agents version,
integration name, and agent name.

---

### Model Resolution

The first thing `create_deep_agent` does is resolve the model:

```python
_model_spec: str | None = model if isinstance(model, str) else None

if model is None:
    warn_deprecated(...)
    model = _build_default_model()
else:
    model = resolve_model(model)
```

The `_model_spec` variable preserves the original string form (if any)
for harness profile resolution. When `model=None`, a deprecation
warning is emitted and the default `claude-sonnet-4-6` is used. The
un-decorated `_build_default_model()` is called instead of
`get_default_model()` so the user-facing deprecation flag on
`get_default_model` is not burned -- direct callers of that function
still see one warning per process.

---

### Harness Profile Resolution

After model resolution, a harness profile is looked up:

```python
_profile = _harness_profile_for_model(model, _model_spec)
```

The profile is determined by the model class and/or model string.
Profiles can customize:

- `base_system_prompt` -- replaces `BASE_AGENT_PROMPT`
- `system_prompt_suffix` -- appended after BASE/CUSTOM
- `excluded_middleware` -- middleware to filter from all stacks
- `excluded_tools` -- tools to filter via `_ToolExclusionMiddleware`
- `tool_description_overrides` -- rewrites for specific tool descriptions
- `extra_middleware` -- additional middleware factories
- `general_purpose_subagent` -- configuration for the auto-added GP subagent

After profile resolution, profile-level invariants are validated:

```python
_validate_excluded_middleware_config(
    _profile,
    required_classes=_REQUIRED_MIDDLEWARE_CLASSES,
    required_names=_REQUIRED_MIDDLEWARE_NAMES,
)
```

This check rejects any attempt to exclude `FilesystemMiddleware` or
`SubAgentMiddleware`, raising `ValueError` with guidance on how to
properly disable specific tools without removing the scaffolding.

---

### Tool Description Overrides

```python
_tools = _apply_tool_description_overrides(
    tools,
    _profile.tool_description_overrides,
)
```

User-supplied tools have their descriptions rewritten according to the
harness profile's `tool_description_overrides` mapping. Tool exclusion
is handled separately by `_ToolExclusionMiddleware`, which filters all
tools (user-supplied and middleware-injected) in one place.

---

### Backend Initialization

```python
backend = backend if backend is not None else StateBackend()
```

When no backend is provided, a `StateBackend()` is created. This stores
files ephemerally in the LangGraph agent state. For persistent file
storage or shell command execution, users should pass a
`FilesystemBackend` or a sandbox backend.

---

### Subagent Processing

Subagent processing is the most complex section of `create_deep_agent`,
spanning approximately 100 lines. The caller-supplied `subagents`
sequence is partitioned into two lists:

```python
inline_subagents: list[SubAgent | CompiledSubAgent] = []
async_subagents: list[AsyncSubAgent] = []
```

The partitioning logic checks for discriminator fields:

1. If `"graph_id"` is present in the spec, it is an `AsyncSubAgent`.
2. If `"runnable"` is present, it is a `CompiledSubAgent` -- used as-is.
3. Otherwise, it is a declarative `SubAgent` requiring full processing.

#### Declarative SubAgent Processing

For each declarative `SubAgent`, the following steps occur:

1. **Model resolution**: The subagent's model defaults to the parent
   model. It is resolved via `resolve_model()`.

2. **Profile resolution**: A per-subagent harness profile is resolved
   based on the subagent's model.

3. **Permission inheritance**: The subagent's permissions default to
   the parent's `permissions` unless the subagent provides its own.

4. **Middleware stack construction**: A fresh middleware stack is built
   for the subagent:
   - `FilesystemMiddleware(backend, custom_tool_descriptions, _permissions)`
   - `create_summarization_middleware(model, backend)`
   - `PatchToolCallsMiddleware()`
   - `SkillsMiddleware(backend, sources)` (if the subagent has skills)
   - User-supplied subagent middleware
   - Profile `extra_middleware`
   - `_ToolExclusionMiddleware` (if profile has `excluded_tools`)
   - `AnthropicPromptCachingMiddleware`

5. **Excluded middleware validation and filtering**: The subagent's
   profile exclusions are validated and applied with separate match
   tracking sets.

6. **Interrupt-on configuration**: The subagent inherits the parent's
   `interrupt_on` unless it provides its own. Filesystem-permission-
   derived interrupt configs are merged in.

7. **Tool inheritance**: The subagent inherits the parent's tools
   unless it declares its own via `spec.get("tools")`.

8. **Prompt application**: The subagent's `system_prompt` is processed
   through `_apply_profile_prompt()`.

---

### General-Purpose Subagent Auto-Addition

After processing all caller-supplied subagents, the function
conditionally auto-adds a default general-purpose subagent:

```python
gp_profile = _profile.general_purpose_subagent or GeneralPurposeSubagentProfile()
if gp_profile.enabled is not False and not any(
    spec["name"] == GENERAL_PURPOSE_SUBAGENT["name"]
    for spec in inline_subagents
):
```

The general-purpose subagent is added unless:

1. The harness profile explicitly disables it via
   `general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)`.
2. The caller already supplied a subagent with the same name as the
   default general-purpose subagent.

The GP subagent gets its own middleware stack:

- `FilesystemMiddleware(backend, tool_description_overrides, _permissions)`
- `create_summarization_middleware(model, backend)`
- `PatchToolCallsMiddleware()`
- `SkillsMiddleware(backend, sources)` (if parent has skills)
- Profile `extra_middleware`
- `_ToolExclusionMiddleware` (if profile has `excluded_tools`)
- `AnthropicPromptCachingMiddleware`

The GP subagent is inserted at position 0 in `inline_subagents`, so
it appears first in the subagent list.

Its prompt can be customized through `gp_profile.system_prompt` (which
overrides the profile's `base_system_prompt`) or defaults to the
standard profile-processed version of `GENERAL_PURPOSE_SUBAGENT`'s
system prompt. The profile suffix is always layered on top.

---

### Main Agent Middleware Stack Assembly

The main agent middleware stack is built in this order:

```python
deepagent_middleware = []
if skills is not None:
    deepagent_middleware.append(SkillsMiddleware(...))  # Skills (conditional)

deepagent_middleware.append(
    FilesystemMiddleware(...)                # Filesystem (required)
)

if inline_subagents:
    sub_agent_middleware = SubAgentMiddleware(...)  # Subagents (conditional)
    deepagent_middleware.append(sub_agent_middleware)

deepagent_middleware.extend([
    create_summarization_middleware(...),    # Summarization
    PatchToolCallsMiddleware(),             # Patch tool calls
])

if async_subagents:
    deepagent_middleware.append(AsyncSubAgentMiddleware(...))  # Async subagents (conditional)

# Harness-profile extras, then prompt caching, then memory form the "tail".
deepagent_middleware.extend(_profile.materialize_extra_middleware())  # Profile extra
append_prompt_caching_middleware(deepagent_middleware)                # AnthropicPromptCachingMiddleware (unconditional)

if memory is not None:
    deepagent_middleware.append(MemoryMiddleware(..., add_cache_control=True))  # Memory (conditional)

if main_interrupt_on is not None:
    deepagent_middleware.append(HumanInTheLoopMiddleware(...))  # HITL (conditional)

# Excluded-middleware filtering runs, then user `middleware=` is spliced in
# via _apply_custom_middleware(..., core_names=...), which inserts custom
# middleware AHEAD of the profile/prompt-caching/memory tail (not a plain
# append). Tool exclusion is appended last.
```

There is **no `TodoListMiddleware`** in the default stack; the todo tool
ships only with harness profiles that opt into LangChain's
`TodoListMiddleware`.

Note the deliberate ordering:

- Profile `extra_middleware` goes between user middleware and memory so
  that memory updates (which change the system prompt) do not
  invalidate the Anthropic prompt cache prefix.

- `AnthropicPromptCachingMiddleware` is unconditional. It uses
  `unsupported_model_behavior="ignore"` so it silently no-ops for
  non-Anthropic models.

- `MemoryMiddleware` uses `add_cache_control=True`, which applies the
  cache control breakpoint only when the request model is Anthropic.

- `HumanInTheLoopMiddleware` is installed only when there are actual
  interrupt configurations (either from `interrupt_on` parameter or
  from filesystem permissions with `mode="interrupt"`).

---

### Excluded Middleware Filtering

After the full stack is assembled, excluded middleware from the harness
profile is filtered out:

```python
deepagent_middleware = _apply_excluded_middleware(
    deepagent_middleware,
    _profile,
    matched_classes=_main_matched_classes,
    matched_names=_main_matched_names,
)
```

The filtering is tracked across both the main agent stack and the GP
subagent stack using shared `_main_matched_classes` and
`_main_matched_names` sets. After filtering, coverage is verified:

```python
_verify_excluded_middleware_coverage(
    _profile,
    _main_matched_classes,
    _main_matched_names,
    required_classes=_REQUIRED_MIDDLEWARE_CLASSES,
    required_names=_REQUIRED_MIDDLEWARE_NAMES,
)
```

This raises `ValueError` if any exclusion entry matched nothing across
both stacks, which is almost certainly a typo or stale profile.

---

### Private State Field Detection

After middleware filtering, private state fields are detected:

```python
private_state_keys = private_state_field_names(
    *(mw.state_schema for mw in deepagent_middleware
      if getattr(mw, "state_schema", None) is not None)
)
if sub_agent_middleware is not None:
    sub_agent_middleware.private_state_keys = private_state_keys
```

Fields annotated with `PrivateStateAttr` in any middleware's
`state_schema` are collected into a frozenset. This set is forwarded
to `SubAgentMiddleware` so that private state fields are not leaked
to subagents.

---

### Final System Prompt Assembly

```python
base_prompt = _apply_profile_prompt(_profile, "")
if system_prompt is None:
    final_system_prompt = base_prompt
elif isinstance(system_prompt, SystemMessage):
    if base_prompt:
        final_system_prompt = SystemMessage(
            content_blocks=[
                *system_prompt.content_blocks,
                {"type": "text", "text": f"\n\n{base_prompt}"}
            ]
        )
    else:
        final_system_prompt = system_prompt
else:
    final_system_prompt = system_prompt + (f"\n\n{base_prompt}" if base_prompt else "")
```

The base prompt is **empty by default** (`_apply_profile_prompt(_profile, "")`);
it is non-empty only when the resolved `HarnessProfile` sets a
`base_system_prompt`. `_apply_profile_prompt` also appends the profile SUFFIX
when present.

---

### Graph Compilation and Return

The final call delegates to LangChain's `create_agent`:

```python
return create_agent(
    model,
    system_prompt=final_system_prompt,
    tools=_tools,
    middleware=deepagent_middleware,
    response_format=response_format,
    context_schema=context_schema,
    checkpointer=checkpointer,
    store=store,
    debug=debug,
    name=name,
    cache=cache,
    state_schema=state_schema if state_schema is not None else DeepAgentState,
).with_config({
    "recursion_limit": 9_999,
    "metadata": {
        "ls_integration": "deepagents",
        "lc_versions": {"deepagents": __version__},
        "lc_agent_name": name,
    },
})
```

Key details:

- `state_schema` defaults to `DeepAgentState` when no custom schema
  is provided, ensuring the `DeltaChannel` optimization is always in
  effect.
- `recursion_limit=9_999` allows very long agent loops without hitting
  LangGraph's default limit.
- Metadata includes the integration name (`"deepagents"`), package
  version, and agent name for observability and tracing.

---

## Middleware Stack Ordering

The base (pre-splice) middleware ordering for the main agent, from first to last:

| Position | Middleware | Condition |
|----------|-----------|-----------|
| 1 | `SkillsMiddleware` | If `skills` is provided |
| 2 | `FilesystemMiddleware` | Always (required scaffolding) |
| 3 | `SubAgentMiddleware` | If inline subagents exist |
| 4 | `SummarizationMiddleware` | Always |
| 5 | `PatchToolCallsMiddleware` | Always |
| 6 | `AsyncSubAgentMiddleware` | If async subagents exist |
| 7 | *Profile `extra_middleware`* | If profile has `extra_middleware` |
| 8 | `AnthropicPromptCachingMiddleware` | Always (no-ops for non-Anthropic) |
| 9 | `MemoryMiddleware` | If `memory` is provided |
| 10 | `HumanInTheLoopMiddleware` | If `interrupt_on` configs exist |

There is **no `TodoListMiddleware`** in the default stack (it is a
harness-profile opt-in). After this base stack is assembled:

1. Profile `excluded_middleware` entries are filtered out.
2. User `middleware=` is spliced in via `_apply_custom_middleware(...,
   core_names=...)`, which inserts it **ahead of** the profile /
   prompt-caching / memory tail (positions 7–9) rather than at the very end.
3. `_ToolExclusionMiddleware` is appended **last** (if the profile has
   `excluded_tools`) so excluded tool names cannot be restored by a custom
   `wrap_model_call`.

---

## Recursion Limit and Metadata

The compiled graph is configured with:

- **`recursion_limit: 9999`** -- effectively unlimited agent loop
  iterations. LangGraph's default is much lower (typically 25).
  Setting this high allows agents to work through long multi-step
  tasks without artificial termination.

- **Metadata**:
  - `ls_integration: "deepagents"` -- identifies the integration for
    LangSmith tracing.
  - `lc_versions: {"deepagents": __version__}` -- package version for
    observability.
  - `lc_agent_name: name` -- the agent's name for tracing.

---

## Architectural Invariants

1. **DeltaChannel is always active.** If no custom `state_schema` is
   provided, `DeepAgentState` is used, which always has the
   `DeltaChannel` wrapper on `messages`. Custom schemas must extend
   `DeepAgentState`, preserving this.

2. **FilesystemMiddleware and SubAgentMiddleware cannot be excluded.**
   They are in `_REQUIRED_MIDDLEWARE` and validation raises
   `ValueError` for any attempt to exclude them.

3. **AnthropicPromptCachingMiddleware is always present.** Even for
   non-Anthropic models, it is included but configured to silently
   no-op.

4. **USER prompt always comes first.** No matter how the profile or
   defaults modify the system prompt, the caller's content is always
   prepended.

5. **SUFFIX always comes last.** Model-tuning guidance from harness
   profiles is always positioned closest to the conversation history.

6. **The general-purpose subagent is always present unless explicitly
   disabled.** It is auto-added unless the profile sets
   `GeneralPurposeSubagentProfile(enabled=False)` or the caller
   provides their own subagent with the same name.

7. **Declarative subagents inherit parent config by default.** Tools,
   permissions, and `interrupt_on` cascade from parent to child
   unless explicitly overridden per subagent.

8. **Private state fields are never leaked to subagents.** The
   `private_state_keys` frozenset is computed from middleware
   `state_schema` annotations and forwarded to `SubAgentMiddleware`.

9. **Excluded middleware coverage must be total.** Every entry in
   `profile.excluded_middleware` must match at least one middleware
   somewhere across the main agent and GP subagent stacks.
   Unmatched entries raise `ValueError` to catch typos and stale
   profiles.

10. **recursion_limit is set to 9999.** This is high enough to be
    effectively unlimited for normal agent operation while still
    providing a safety net against true infinite loops.
