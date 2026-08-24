# 20 -- Profiles: Provider and Harness Configuration

## Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `libs/deepagents/deepagents/profiles/__init__.py` | ~39 | Public API surface -- re-exports `ProviderProfile`, `HarnessProfile`, `HarnessProfileConfig`, `GeneralPurposeSubagentProfile`, `register_harness_profile`, `register_provider_profile` |
| `libs/deepagents/deepagents/profiles/harness/harness_profiles.py` | ~1321 | HarnessProfile dataclass, merge logic, registry, prompt assembly, serialization, validation |
| `libs/deepagents/deepagents/profiles/provider/provider_profiles.py` | ~455 | ProviderProfile dataclass, merge logic, registry, `apply_provider_profile()` |
| `libs/deepagents/deepagents/profiles/_builtin_profiles.py` | ~234 | Lazy bootstrap, thread safety, entry-point plugin discovery, rollback-on-failure |
| `libs/deepagents/deepagents/profiles/_keys.py` | ~50 | `validate_profile_key()` -- grammar guard for registry keys |
| `libs/deepagents/deepagents/profiles/provider/_openai.py` | ~20 | Built-in: OpenAI Responses API default |
| `libs/deepagents/deepagents/profiles/provider/_openrouter.py` | ~90 | Built-in: OpenRouter version check, attribution headers, Azure block |
| `libs/deepagents/deepagents/profiles/harness/_anthropic_haiku_4_5.py` | ~60 | Built-in: Anthropic Haiku 4.5 prompt suffix |
| `libs/deepagents/deepagents/profiles/harness/_anthropic_sonnet_4_6.py` | ~60 | Built-in: Anthropic Sonnet 4.6 prompt suffix |
| `libs/deepagents/deepagents/profiles/harness/_anthropic_opus_4_7.py` | ~80 | Built-in: Anthropic Opus 4.7 prompt suffix (tool + subagent guidance) |
| `libs/deepagents/deepagents/profiles/harness/_openai_codex.py` | ~70 | Built-in: OpenAI Codex prompt suffix (3 model specs) |
| `libs/deepagents/deepagents/profiles/provider/_nvidia.py` | — | Built-in: NVIDIA provider profile |
| `libs/deepagents/deepagents/profiles/harness/_nvidia_nemotron_3_ultra.py` | — | Built-in: NVIDIA Nemotron 3 Ultra harness profile |

---

## 1. Two Parallel Registries

Deep Agents maintains two completely independent profile registries, each governing a different phase of agent construction.

### HarnessProfile Registry (`_HARNESS_PROFILES`)

**Phase**: Post-model-construction -- applied by `create_deep_agent`.

**What it controls**:
- System prompt assembly (base prompt replacement, suffix text)
- Tool visibility (which tools are excluded from the model's view)
- Tool description overrides (custom descriptions per tool name)
- Middleware composition (extra middleware to inject, middleware to exclude)
- General-purpose subagent configuration (enable/disable, custom description, custom prompt)

**Storage**: `_HARNESS_PROFILES: dict[str, HarnessProfile]` in `harness_profiles.py` (line 935). This is a plain dict whose reference identity is preserved across bootstrap rollbacks.

**Lookup function**: `_get_harness_profile(spec)` (line 1045), with a higher-level wrapper `_harness_profile_for_model(model, spec)` (line 1250) for pre-built model instances.

### ProviderProfile Registry (`_PROVIDER_PROFILES`)

**Phase**: Model-construction -- applied by `resolve_model()` via `apply_provider_profile()`.

**What it controls**:
- Static kwargs passed to `init_chat_model` (e.g. `use_responses_api=True`)
- Pre-initialization hooks (side effects like version checks that run before model construction)
- Dynamic kwargs factories (callables that produce kwargs from runtime state like env vars)

**Storage**: `_PROVIDER_PROFILES: dict[str, ProviderProfile]` in `provider_profiles.py` (line 165). Same plain-dict identity-preservation guarantee as the harness registry.

**Lookup function**: `get_provider_profile(spec)` (line 249), with the composition helper `apply_provider_profile(spec, kwargs)` (line 317) that handles lookup + pre_init + kwargs merging.

### Why Two Registries

The split reflects a fundamental separation of concerns:

- **ProviderProfile** answers: "How should the model object be constructed?" This is provider-specific (OpenAI needs `use_responses_api`, OpenRouter needs attribution headers).
- **HarnessProfile** answers: "How should the agent behave once built?" This is model-specific (Opus 4.7 needs subagent usage guidance, Codex models need autonomous-engineer instructions).

A single model spec like `"openai:gpt-5.4"` can match profiles in both registries independently. The provider profile fires during `resolve_model()`, and the harness profile fires during `create_deep_agent()`.

---

## 2. Profile Data Types

### 2.1 ProviderProfile (frozen dataclass)

Defined in `provider/provider_profiles.py` at line 37. Controls model construction by injecting kwargs into `init_chat_model`.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `init_kwargs` | `Mapping[str, Any]` | `{}` (frozen to `MappingProxyType` in `__post_init__`) | Static kwargs forwarded to `init_chat_model`. Factory output overrides on key collision. |
| `pre_init` | `Callable[[str], None] \| None` | `None` | Called with raw model spec before initialization. Raise to abort model construction. |
| `init_kwargs_factory` | `Callable[[], dict[str, Any]] \| None` | `None` | Factory producing dynamic kwargs at resolution time (e.g. env-var-based). Output overrides `init_kwargs` on shared keys. |

The `__post_init__` hook (line 131) wraps `init_kwargs` in `MappingProxyType(dict(...))` to prevent post-construction mutation of the mapping.

### 2.2 HarnessProfile (frozen dataclass)

Defined in `harness/harness_profiles.py` at line 483. Controls agent runtime behavior -- prompt assembly, tool visibility, middleware, subagent configuration. Used by `create_deep_agent`.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `base_system_prompt` | `str \| None` | `None` | `CUSTOM` slot -- completely replaces `BASE_AGENT_PROMPT` when set. |
| `system_prompt_suffix` | `str \| None` | `None` | `SUFFIX` slot -- appended to assembled base prompt with `"\n\n"` separator. |
| `tool_description_overrides` | `Mapping[str, str]` | `{}` (frozen to `MappingProxyType`) | Per-tool description replacements keyed by tool name. |
| `excluded_tools` | `frozenset[str]` | `frozenset()` | Tool names to remove from the tool set. Additive on merge. |
| `excluded_middleware` | `frozenset[type[AgentMiddleware] \| str]` | `frozenset()` | Middleware to strip. Accepts classes or string names. Cannot exclude `FilesystemMiddleware` or `SubAgentMiddleware`. |
| `extra_middleware` | `Sequence[AgentMiddleware] \| Callable[[], Sequence[AgentMiddleware]]` | `()` | Middleware appended to every runtime stack. Can be static tuple or zero-arg factory. Runtime-only (not in config). |
| `general_purpose_subagent` | `GeneralPurposeSubagentProfile \| None` | `None` | Edits for the auto-added general-purpose subagent. |

The `__post_init__` hook (line 722) performs several defensive operations:
- Freezes `tool_description_overrides` into `MappingProxyType`
- Copies `extra_middleware` to tuple if not already a tuple or callable
- Validates every `excluded_middleware` entry against string grammar rules and scaffolding restrictions

**Methods:**
- `materialize_extra_middleware() -> list[AgentMiddleware]` (line 770): Returns a fresh list of extra middleware, invoking the factory if `extra_middleware` is a callable.

### 2.3 HarnessProfileConfig (frozen dataclass)

Defined in `harness/harness_profiles.py` at line 192. The declarative/file-friendly subset of `HarnessProfile`, suitable for YAML/JSON serialization. Contains the same fields as `HarnessProfile` except `extra_middleware` is absent.

| Field | Type | Default |
|-------|------|---------|
| `base_system_prompt` | `str \| None` | `None` |
| `system_prompt_suffix` | `str \| None` | `None` |
| `tool_description_overrides` | `Mapping[str, str]` | `{}` |
| `excluded_tools` | `frozenset[str]` | `frozenset()` |
| `excluded_middleware` | `frozenset[str]` | `frozenset()` (string-only, no class form) |
| `general_purpose_subagent` | `GeneralPurposeSubagentProfile \| None` | `None` |

**Methods:**

- `to_dict() -> dict[str, Any]` (line 339): Omits fields at their default value for minimal serialization output.
- `from_dict(data) -> HarnessProfileConfig` (classmethod, line 374): Constructs from a plain dict. Rejects unknown keys with `TypeError`. Uses internal coercion helpers: `_coerce_str_or_none`, `_coerce_str_mapping`, `_coerce_frozen_strset`, `_coerce_general_purpose_subagent`.
- `to_harness_profile() -> HarnessProfile` (line 407): Lossless conversion to runtime form (config is a strict subset).
- `from_harness_profile(profile) -> HarnessProfileConfig` (classmethod, line 440): Exports back to config form. Raises `ValueError` if the profile has non-empty `extra_middleware` (runtime-only, not serializable). Class-form `excluded_middleware` entries require a `serialized_name` attribute for stable round-trips.

### 2.4 GeneralPurposeSubagentProfile (frozen dataclass)

Defined in `harness/harness_profiles.py` at line 83. Per-model configuration edits for the auto-added `general-purpose` subagent.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `enabled` | `bool \| None` | `None` | Three-state: `None` = inherit/default on; `True` = force inclusion; `False` = disable. |
| `description` | `str \| None` | `None` | Override the default subagent description. |
| `system_prompt` | `str \| None` | `None` | Override the default GP subagent system prompt. Takes precedence over `HarnessProfile.base_system_prompt` for the GP subagent specifically. |

**Methods:**

- `to_dict() -> dict[str, Any]` (line 138): Only emits fields with non-`None` values.
- `from_dict(data) -> GeneralPurposeSubagentProfile` (classmethod, line 158): Validates types. Unknown keys raise `TypeError`.

---

## 3. Profile Lookup: Resolution Order

Both registries use identical three-step resolution logic. Given a spec like `"openai:gpt-5.4"`:

### Step 1: Exact Match
Look up `"openai:gpt-5.4"` in the registry. If found, this is the `exact` profile.

### Step 2: Provider Prefix
Extract the provider portion before the first colon (`"openai"`). Look up `"openai"` in the registry. If found, this is the `base` profile.

### Step 3: Merge or Return
- **Both exist**: Merge `base` and `exact`, with `exact` winning on conflicts. Return merged.
- **Only exact**: Return `exact`.
- **Only base**: Return `base`. Log a debug breadcrumb noting that no exact profile matched.
- **Neither**: Return `None` (HarnessProfile falls back to an empty default; ProviderProfile returns unchanged kwargs).

### Guard Rails on Malformed Specs

Before consulting the registry, both lookup functions reject:
- Empty strings
- Specs with more than one colon (e.g. `"a:b:c"`)
- Specs with an empty provider or model half (e.g. `"openai:"` or `":gpt-5"`)

These return `None` immediately, preventing a spec like `"openai:"` from silently matching the `"openai"` provider-level registration.

### `_harness_profile_for_model(model, spec)` (line 1250)

Used when the caller passes a pre-built `BaseChatModel` to `create_deep_agent`. Resolution order:
1. Try the spec (if provided) directly via `_get_harness_profile`.
2. Try `{provider}:{identifier}` constructed from `get_model_provider()` and `get_model_identifier()`.
3. Try the identifier alone if it contains a colon (some providers embed provider info in the identifier).
4. Try the provider alone.
5. Fall back to a default empty `HarnessProfile()`.

### `_has_any_harness_profile() -> bool` (line 1026)

Returns `True` when the user has registered harness profiles beyond the bootstrap-provided defaults. Computed by subtracting `_BOOTSTRAP_HARNESS_KEYS` from the live registry. Used to control logging verbosity: profile-miss logs escalate from `DEBUG` to `WARNING` when user profiles exist but none matched.

---

## 4. Key Validation (`validate_profile_key`)

Registration keys are validated by `validate_profile_key()` from `_keys.py` (lines 1-43). The function enforces the `provider` or `provider:model` key shape. Raises `ValueError` for:

- Empty string
- Leading or trailing whitespace
- More than one colon
- Empty provider or model half around the colon
- Whitespace adjacent to the colon

```python
# Valid keys
validate_profile_key("openai")           # provider-wide
validate_profile_key("openai:gpt-5.4")   # exact model

# Invalid keys -- all raise ValueError
validate_profile_key("")                  # empty
validate_profile_key("openai:")           # empty model half
validate_profile_key(":gpt-5")           # empty provider half
validate_profile_key("a:b:c")            # multiple colons
validate_profile_key(" openai")           # leading whitespace
validate_profile_key("openai :gpt-5")    # whitespace adjacent to colon
```

---

## 5. Registration API

### `register_harness_profile(key, profile)` (line 975)

Accepts both `HarnessProfile` and `HarnessProfileConfig`. Config objects are automatically converted to runtime profiles via `to_harness_profile()` at registration time. Internally:
1. Calls `_ensure_harness_profiles_loaded()` to trigger lazy bootstrap.
2. Delegates to `_register_harness_profile_impl(key, profile)`.
3. The impl function validates the key, coerces config to runtime profile, and merges additively via `_merge_profiles` if the key already exists.

```python
from deepagents import HarnessProfile, HarnessProfileConfig, register_harness_profile

# Runtime profile (supports extra_middleware, class-form excluded_middleware)
register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfile(system_prompt_suffix="Think step by step."),
)

# Declarative config (YAML/JSON-friendly, string-only excluded_middleware)
register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfileConfig(
        system_prompt_suffix="Think step by step.",
        excluded_middleware={"SummarizationMiddleware"},
    ),
)
```

### `register_provider_profile(key, profile)` (line 194)

Accepts only `ProviderProfile` (no config variant exists because `pre_init` and `init_kwargs_factory` are inherently non-serializable). Internally:
1. Calls `_ensure_provider_profiles_loaded()` to trigger lazy bootstrap.
2. Delegates to `_register_provider_profile_impl(key, profile)`.
3. The impl function (line 176) validates the key via `validate_profile_key(key)` and merges additively via `_merge_provider_profiles` if the key already exists.

```python
from deepagents import ProviderProfile, register_provider_profile

register_provider_profile(
    "openai",
    ProviderProfile(init_kwargs={"temperature": 0.7}),
)
```

### Lookup Functions

**`get_provider_profile(spec) -> ProviderProfile | None`** (line 249): Resolution order is exact match on spec, then provider prefix (before `:`), then `None`. When both exist, they are merged (exact overrides provider). Malformed specs return `None`.

**`apply_provider_profile(spec, kwargs, *, run_pre_init=True) -> dict[str, Any]`** (line 317): Composes lookup + `pre_init` execution + kwargs merging. Precedence from lowest to highest:
1. `profile.init_kwargs` (static defaults from the profile)
2. `profile.init_kwargs_factory()` output (dynamic defaults)
3. `kwargs` argument (caller-supplied, overrides everything)

### Registration Order

Both functions call `_ensure_builtin_profiles_loaded()` before performing the registration. This means:
1. The first call to any registration or lookup function triggers the lazy bootstrap.
2. Built-in profiles load first.
3. Third-party plugins load next.
4. The user's registration then merges on top.

---

## 6. Additive Merge Semantics

When a profile is registered under a key that already exists, the new profile is **merged on top** of the existing one rather than replacing it. This is the core composability mechanism.

### HarnessProfile Merge Rules (`_merge_profiles`, line 1192)

| Field | Merge Behavior |
|-------|---------------|
| `base_system_prompt` | Override wins if not `None`; otherwise base preserved |
| `system_prompt_suffix` | Override wins if not `None`; otherwise base preserved |
| `tool_description_overrides` | Dict merge: `{**base, **override}` -- override wins per key |
| `excluded_tools` | Set union: `base \| override` -- both sets combined |
| `excluded_middleware` | Set union: `base \| override` -- both sets combined |
| `extra_middleware` | Type-based merge via `_merge_middleware()` (see below) |
| `general_purpose_subagent` | Field-by-field merge via `_merge_general_purpose_subagent_profiles()` |

### Middleware Merge (`_merge_middleware`, line 1114)

Middleware stacks enforce at most one instance of each concrete class. The merge uses type identity as the key:

1. Walk the base sequence. For each entry:
   - If the override has an instance of the same `type()`, replace the base instance at the same position.
   - Otherwise, keep the base instance.
2. Append any override instances whose types did not appear in the base.
3. If a type appears multiple times in the base, only the first occurrence is replaced; later duplicates are dropped.

The result is returned via a **factory closure** so both base and override sequences (which may themselves be factories) are resolved lazily at each lookup.

```python
# Example:
# base:     [MiddlewareA(x=1), MiddlewareB(y=2)]
# override: [MiddlewareA(x=99), MiddlewareC(z=3)]
# merged:   [MiddlewareA(x=99), MiddlewareB(y=2), MiddlewareC(z=3)]
#            ^-- replaced in place    ^-- kept        ^-- appended
```

### ProviderProfile Merge Rules (`_merge_provider_profiles`, line 382)

| Field | Merge Behavior |
|-------|---------------|
| `init_kwargs` | Dict merge: `{**base, **override}` -- override wins per key |
| `pre_init` | Chained: base runs first, then override. Exception in base halts chain. |
| `init_kwargs_factory` | Chained: both run (base first, then override), outputs merged with override winning per key |

### GeneralPurposeSubagentProfile Merge (`_merge_general_purpose_subagent_profiles`, line 1176)

| Field | Merge Behavior |
|-------|---------------|
| `enabled` | Override wins if not `None` |
| `description` | Override wins if not `None` |
| `system_prompt` | Override wins if not `None` |

This means a model-level `enabled=True` can re-enable a subagent that a provider-level profile disabled with `enabled=False`, and vice versa.

### Merge at Registration vs. Lookup

Merge happens at **two** distinct points:

1. **Registration time** (`_register_harness_profile_impl`, `_register_provider_profile_impl`): When registering under a key that already has a profile, the new profile merges on top and the merged result replaces the stored entry.
2. **Lookup time** (`_get_harness_profile`, `get_provider_profile`): When both an exact-model profile and a provider-level profile exist for a query, they are merged on the fly with the exact-model profile as the override.

---

## 7. HarnessProfile Fields -- Detailed Semantics

### `base_system_prompt: str | None` (default: `None`)

The `CUSTOM` slot in prompt assembly. When set, **completely replaces** `BASE_AGENT_PROMPT` as the base prompt. When `None`, `BASE_AGENT_PROMPT` is used unchanged.

If both `base_system_prompt` and `system_prompt_suffix` are set, the suffix is appended to the custom base.

### `system_prompt_suffix: str | None` (default: `None`)

The `SUFFIX` slot in prompt assembly. Text appended to the assembled base system prompt with a blank-line separator (`"\n\n"`). Always sits last so model-tuning guidance lands closest to the conversation history.

Applied uniformly to every assembled stack: the main agent, declarative subagents, and the auto-added general-purpose subagent.

### `tool_description_overrides: Mapping[str, str]` (default: `{}`)

Per-tool description replacements keyed by tool name. Applied to built-in filesystem tools, the `task` tool, and user-supplied `BaseTool` or dict tools. Plain callable tools are left unchanged.

Frozen at construction into a `MappingProxyType` to prevent post-construction mutation.

**Warning for the `task` tool**: The default `task` tool description contains an `{available_agents}` format placeholder. If your override does not include this placeholder, the model will not see which subagents exist.

### `excluded_tools: frozenset[str]` (default: `frozenset()`)

Tool names to remove from the tool set. Applied via a tool-exclusion middleware after tool-injecting middleware has run, so it can remove both user-supplied tools and tools added by Deep Agents middleware.

Exclusions are additive when merging: provider excludes `execute` + exact-model excludes `grep` = merged excludes both.

### `excluded_middleware: frozenset[type[AgentMiddleware] | str]` (default: `frozenset()`)

Middleware to strip from every stack this profile applies to. Entries may be:

- **Class form**: Matched by exact type (`type(m) is cls`), not `isinstance`. Typos surface at import time.
- **String form**: Matched by `AgentMiddleware.name` exactly. For YAML/JSON profiles and private middleware with public aliases.

**Grammar checks at construction time**:
- Empty/whitespace strings raise `ValueError`
- Colon-containing strings raise `ValueError` (class-path `module:Class` reserved for future)
- Underscore-prefixed names raise `ValueError` (private middleware not in public exclusion surface)

**Scaffolding restrictions**: `FilesystemMiddleware` and `SubAgentMiddleware` cannot be excluded (class form or name form). Use `excluded_tools` to hide their tools, or `general_purpose_subagent.enabled=False` to remove the `task` tool.

### `extra_middleware: Sequence[AgentMiddleware] | Callable[[], Sequence[AgentMiddleware]]` (default: `()`)

Middleware appended to every runtime middleware stack (main agent, GP subagent, declarative sync subagents). Not applied to `CompiledSubAgent` or `AsyncSubAgent`.

May be a static sequence or a zero-arg factory. Factory is called at each lookup, allowing fresh instances per stack. Frozen at construction: sequences are copied to tuples; factories are stored as-is.

**Runtime-only**: Intentionally absent from `HarnessProfileConfig` because middleware instances cannot be represented in YAML/JSON.

### `general_purpose_subagent: GeneralPurposeSubagentProfile | None` (default: `None`)

Sub-profile controlling the auto-added `general-purpose` subagent. `None` is equivalent to the default-constructed sub-profile (stock description and prompt).

**Precedence note**: When a profile sets both `general_purpose_subagent.system_prompt` and `base_system_prompt`, the GP-specific system prompt wins for the general-purpose subagent (more specific intent wins).

---

## 8. ProviderProfile Fields -- Detailed Semantics

### `init_kwargs: Mapping[str, Any]` (default: `{}`)

Static keyword arguments forwarded to `init_chat_model`. Frozen at construction into `MappingProxyType` to prevent post-construction mutation.

When both `init_kwargs` and `init_kwargs_factory` are set, the factory's output overrides `init_kwargs` on key collision.

### `pre_init: Callable[[str], None] | None` (default: `None`)

Optional callable invoked with the raw model spec before initialization. Runs before `init_kwargs_factory` and before `init_chat_model`. If it raises, model construction is aborted.

Use for side-effectful checks like minimum-version enforcement.

### `init_kwargs_factory: Callable[[], dict[str, Any]] | None` (default: `None`)

Optional factory producing dynamic init kwargs at resolution time. Use when values depend on runtime state such as environment variables.

Precedence within a single profile: factory output overrides `init_kwargs` on shared keys.

When merging two profiles with factories, both run at every resolution (base first, then override), and their outputs merge with the override's values winning on shared keys.

---

## 9. Serialization and Round-Tripping

### HarnessProfileConfig: The Declarative Subset

`HarnessProfileConfig` is the YAML/JSON-friendly subset of `HarnessProfile`. It includes only fields that can be represented as plain strings, bools, lists, and nested dicts. The runtime-only `extra_middleware` field is absent.

#### `to_dict() -> dict[str, Any]`

Dumps to a plain dict suitable for `json.dumps` or `yaml.safe_dump`. Fields at their default are omitted for minimal output.

```python
config = HarnessProfileConfig(
    system_prompt_suffix="Think step by step.",
    excluded_middleware={"SummarizationMiddleware"},
)
config.to_dict()
# {"system_prompt_suffix": "Think step by step.", "excluded_middleware": ["SummarizationMiddleware"]}
```

#### `from_dict(data) -> HarnessProfileConfig`

Constructs from a plain dict. Unknown keys raise `TypeError`. Excluded-middleware entries are grammar-checked. Uses internal coercion helpers:
- `_coerce_str_or_none(value, field_name)` (line 814)
- `_coerce_str_mapping(value, field_name)` (line 822)
- `_coerce_frozen_strset(value, field_name)` (line 838)
- `_coerce_general_purpose_subagent(value)` (line 854)

```python
config = HarnessProfileConfig.from_dict({
    "system_prompt_suffix": "Think step by step.",
    "excluded_middleware": ["SummarizationMiddleware"],
})
```

#### `to_harness_profile() -> HarnessProfile`

Converts to a runtime profile. Lossless because `HarnessProfileConfig` carries only the file-friendly subset.

#### `from_harness_profile(profile) -> HarnessProfileConfig`

Exports back to config form. **Raises** when the runtime profile contains runtime-only state (`extra_middleware`). Class-form `excluded_middleware` entries require a `serialized_name` attribute for stable serialization. Without it, `_serialize_runtime_excluded_middleware_entry` (lines 925-932) raises `ValueError` with a message explaining that arbitrary class-path serialization is not supported.

### GeneralPurposeSubagentProfile Serialization

#### `to_dict() -> dict[str, Any]`

Only emits fields with non-`None` values.

#### `from_dict(data) -> GeneralPurposeSubagentProfile`

Validates types. Unknown keys raise `TypeError`.

### Round-Trip Guarantee

The serialization is designed to round-trip cleanly:

```python
original = HarnessProfileConfig(
    system_prompt_suffix="Think step by step.",
    excluded_middleware={"SummarizationMiddleware"},
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
)
reconstructed = HarnessProfileConfig.from_dict(original.to_dict())
# reconstructed has identical field values to original
```

The distinction between "explicit empty sub-profile" (`GeneralPurposeSubagentProfile()`) and "no sub-profile" (`None`) is preserved: `to_dict()` emits the `general_purpose_subagent` key even when the sub-profile has no fields set.

### The `serialized_name` Convention

When converting a runtime `HarnessProfile` back to a `HarnessProfileConfig`, class-form `excluded_middleware` entries must be serialized to strings. This only works when the middleware class advertises a `serialized_name: ClassVar[str]` alias. For example, `_DeepAgentsSummarizationMiddleware` exposes `serialized_name = "SummarizationMiddleware"` so it can be excluded by public alias and survive round-trip serialization.

If a class-form entry has no `serialized_name`, the conversion raises `ValueError` rather than silently dropping the exclusion or inventing an unstable name.

---

## 10. Lazy Bootstrap: Thread-Safe, Re-Entrant

The `_ensure_builtin_profiles_loaded()` function in `_builtin_profiles.py` is the single entry point for profile initialization. It has three critical properties.

### Module-Level State

| Variable | Type | Purpose |
|----------|------|---------|
| `_loaded` | `bool` (line 74) | Permanent flag; `True` after successful bootstrap. All subsequent calls short-circuit. |
| `_BOOTSTRAP_CONDITION` | `threading.Condition` (line 84) | Coordinates threads during bootstrap. |
| `_loading_thread_id` | `int \| None` (line 94) | Identifies the thread performing bootstrap. Enables re-entrant detection. |
| `_BOOTSTRAP_HARNESS_KEYS` | `frozenset[str]` (line 62) | Snapshot of harness keys after bootstrap. Used by `_has_any_harness_profile()`. |

### Thread Safety via `_BOOTSTRAP_CONDITION`

A `threading.Condition` coordinates access:
- The first thread to enter acquires ownership by setting `_loading_thread_id` to its thread ID.
- Concurrent threads block on `_BOOTSTRAP_CONDITION.wait()` until the bootstrap thread calls `notify_all()`.
- After completion, `_loaded = True` is set and all subsequent calls short-circuit immediately.

### Re-Entrant Safety

During bootstrap, built-in profile modules and third-party plugins call `register_*_profile()`, which in turn calls `_ensure_builtin_profiles_loaded()`. Without re-entrancy protection, this would deadlock.

The solution: `_loading_thread_id` tracks which thread is currently bootstrapping. When the same thread re-enters (line 137), it sees `_loading_thread_id == thread_id` and returns immediately, allowing the nested registration to proceed against the partially populated registry.

Cross-thread concurrent access (line 139) waits on `_BOOTSTRAP_CONDITION` until bootstrap completes.

```python
# Thread A enters _ensure_builtin_profiles_loaded()
#   -> sets _loading_thread_id = A
#   -> calls _openai.register()
#     -> calls register_provider_profile("openai", ...)
#       -> calls _ensure_builtin_profiles_loaded()
#         -> sees _loading_thread_id == current thread
#         -> returns immediately (re-entrant short-circuit)
#       -> _register_provider_profile_impl("openai", ...) succeeds
#   -> calls _openrouter.register()
#   -> ... (continues bootstrap)
#   -> sets _loaded = True, _loading_thread_id = None
#   -> notifies all waiting threads
```

### Rollback on Failure

If any built-in profile registration throws, the bootstrap:
1. Logs the exception
2. Restores `_PROVIDER_PROFILES` and `_HARNESS_PROFILES` to their pre-bootstrap state using saved snapshots
3. Restores `_BOOTSTRAP_HARNESS_KEYS` to its pre-bootstrap value
4. Clears `_loading_thread_id` and notifies waiting threads
5. Re-raises the exception

The restore is done **in place** (`.clear()` + `.update()`) because other modules hold direct references to the registry dict objects. Creating new dicts would leave those references pointing at stale, empty dicts.

### Bootstrap Execution Order

```python
# Phase 1: Built-in registrations (exceptions propagate)
_openai.register()           # ProviderProfile: use_responses_api=True
_openrouter.register()       # ProviderProfile: version check + attribution
_anthropic_opus_4_7.register()    # HarnessProfile: tool + subagent guidance
_anthropic_sonnet_4_6.register()  # HarnessProfile: universal Claude guidance
_anthropic_haiku_4_5.register()   # HarnessProfile: universal Claude guidance
_openai_codex.register()          # HarnessProfile: autonomous engineer guidance

# Phase 2: Third-party plugins (failures logged + skipped)
_invoke_profile_plugins("deepagents.provider_profiles")
_invoke_profile_plugins("deepagents.harness_profiles")

# Phase 3: Snapshot harness keys for _has_any_harness_profile()
_BOOTSTRAP_HARNESS_KEYS = frozenset(_HARNESS_PROFILES)
```

---

## 11. Plugin System

Third-party packages can register profiles by declaring entry points under two groups.

### Entry-Point Groups

| Group | Constant | Purpose |
|-------|----------|---------|
| `deepagents.provider_profiles` | `_PROVIDER_PROFILE_GROUP` (line 56) | Plugins that call `register_provider_profile()` |
| `deepagents.harness_profiles` | `_HARNESS_PROFILE_GROUP` (line 59) | Plugins that call `register_harness_profile()` |

### Entry-Point Contract

Each entry point must resolve to a **zero-arg callable** that performs its registrations when invoked. The callable's return value is ignored.

```toml
# pyproject.toml for a third-party plugin
[project.entry-points."deepagents.provider_profiles"]
my_provider = "my_package.profiles:register_my_provider"

[project.entry-points."deepagents.harness_profiles"]
my_model = "my_package.profiles:register_my_model"
```

```python
# my_package/profiles.py
from deepagents import ProviderProfile, HarnessProfile
from deepagents import register_provider_profile, register_harness_profile

def register_my_provider():
    register_provider_profile(
        "my_provider",
        ProviderProfile(init_kwargs={"base_url": "https://api.myprovider.com"}),
    )

def register_my_model():
    register_harness_profile(
        "my_provider:my-model-v2",
        HarnessProfile(system_prompt_suffix="Custom guidance for my-model-v2."),
    )
```

### Failure Isolation

The `_invoke_profile_plugins()` function (line 177) differentiates four failure modes:

1. **`entry_points()` itself raises** (e.g. malformed `dist-info` metadata): Logged at `WARNING`. Entire group skipped.
2. **`ep.load()` raises** (missing dependency, import-time error): Logged at `ERROR` with source distribution name (formatted via `_format_plugin_label(ep)`, line 42). Plugin skipped.
3. **Entry point is not callable**: Logged at `ERROR`. Plugin skipped.
4. **Registration callable raises**: Logged at `ERROR`. Plugin skipped. Its registrations are silently absent.

Each failure also emits a `warnings.warn()` so the issue surfaces even when logging is not configured.

### Load Order and Composability

Built-ins load first. Third-party plugins load second. Because registration is additive, a plugin registering under the same key as a built-in **layers on top** rather than replacing. For example, a plugin could add a `system_prompt_suffix` to the existing `"openai"` harness profile without wiping out the built-in's other settings.

There is no ordering guarantee between third-party plugins within the same entry-point group.

---

## 12. Built-in Profiles

### Provider Profiles

#### OpenAI (`_openai.py`)

**Key**: `"openai"` (provider-wide)

**Registration**:
```python
register_provider_profile(
    "openai",
    ProviderProfile(init_kwargs={"use_responses_api": True}),
)
```

**Purpose**: Enables the OpenAI Responses API by default for all `openai:*` models. This is the SDK's preferred OpenAI integration path.

#### OpenRouter (`_openrouter.py`)

**Key**: `"openrouter"` (provider-wide)

**Registration** uses all three ProviderProfile mechanisms:

1. **`pre_init` hook**: Calls `check_openrouter_version()` which enforces `langchain-openrouter >= 0.2.0` (constant `OPENROUTER_MIN_VERSION = "0.2.0"`). Raises `ImportError` with a clear message if the package is missing or too old. Skips the check if the package is not installed or the version string is non-PEP-440.

2. **`init_kwargs_factory`**: The `_openrouter_attribution_kwargs()` function injects app-attribution headers at runtime:
   - `app_url`: `"https://github.com/langchain-ai/deepagents"` (constant `_OPENROUTER_APP_URL`) unless `OPENROUTER_APP_URL` env is set.
   - `app_title`: `"Deep Agents"` (constant `_OPENROUTER_APP_TITLE`) unless `OPENROUTER_APP_TITLE` env is set.
   - Azure provider filtering: `openrouter_provider={"ignore": ["azure"]}` by default. Opt out by setting `DEEPAGENTS_OPENROUTER_ALLOW_AZURE` (constant `_OPENROUTER_ALLOW_AZURE_ENV`) to a truthy value.

### Harness Profiles

#### Anthropic Haiku 4.5 (`_anthropic_haiku_4_5.py`)

**Key**: `"anthropic:claude-haiku-4-5"`

**Suffix contents** (three XML-tagged sections, universal across Claude models):

1. `<use_parallel_tool_calls>` -- Enable parallel tool execution
2. `<investigate_before_answering>` -- Read files before answering code questions
3. `<tool_result_reflection>` -- Reflect on tool results before deciding next steps

No Haiku-specific overlays. Exists as an intentional audit anchor per Anthropic's prompting guide.

#### Anthropic Sonnet 4.6 (`_anthropic_sonnet_4_6.py`)

**Key**: `"anthropic:claude-sonnet-4-6"`

**Suffix contents**: Same three universal Claude guidance sections as Haiku 4.5. No Sonnet-specific overlays. API-level configuration (adaptive thinking, budget_tokens) is handled separately from the profile system. Documented as an intentional audit anchor.

#### Anthropic Opus 4.7 (`_anthropic_opus_4_7.py`)

**Key**: `"anthropic:claude-opus-4-7"`

**Suffix contents** (five XML-tagged sections):

1. `<use_parallel_tool_calls>` -- Universal Claude parallel tool guidance
2. `<investigate_before_answering>` -- Read files before answering
3. `<tool_result_reflection>` -- Reflect on tool results
4. `<tool_usage>` -- **Opus 4.7-specific**: Use tools to observe state directly (counters the model's documented tendency to use tools less aggressively)
5. `<subagent_usage>` -- **Opus 4.7-specific**: Guidance on when to spawn subagents vs. work directly; do not spawn subagents for single-response work; fan out when reading multiple files

The two extra sections address Opus 4.7's behavioral tendencies identified during development.

#### OpenAI Codex (`_openai_codex.py`)

**Keys**: Three model specs registered from the `_CODEX_MODEL_SPECS` tuple (line 22-26):
- `"openai:gpt-5.1-codex"`
- `"openai:gpt-5.2-codex"`
- `"openai:gpt-5.3-codex"`

A single `HarnessProfile` instance is shared across all three registrations.

**Suffix contents** (three markdown sections):

1. **Codex-Specific Behavior**: Autonomous senior engineer demeanor, persist end-to-end, bias to action, no upfront preambles or plans
2. **Parallel Tool Use**: Batch independent operations, avoid sequential tool calls when not necessary
3. **Plan Hygiene**: Reconcile all TODOs/plan items via `write_todos` before finishing

---

## 13. System Prompt Assembly

The system prompt is assembled in a fixed order. The `_apply_profile_prompt()` function (line 778) implements the overlay logic.

### Assembly Order

```
USER (caller-supplied system_prompt from create_deep_agent)
    |
    v
BASE (BASE_AGENT_PROMPT) --or-- CUSTOM (profile.base_system_prompt if not None)
    |
    v
SUFFIX (profile.system_prompt_suffix if not None, joined by "\n\n")
```

### Implementation

```python
def _apply_profile_prompt(profile: HarnessProfile, base_prompt: str) -> str:
    prompt = profile.base_system_prompt if profile.base_system_prompt is not None else base_prompt
    if profile.system_prompt_suffix is not None:
        prompt = prompt + "\n\n" + profile.system_prompt_suffix
    return prompt
```

### Applied Uniformly

The same overlay logic runs for:
- **Main agent**: `base_prompt = BASE_AGENT_PROMPT`
- **Declarative subagents**: `base_prompt = spec["system_prompt"]`
- **General-purpose subagent**: `base_prompt = GP base prompt` (overridable via `general_purpose_subagent.system_prompt`)

---

## 14. HarnessProfileConfig vs. HarnessProfile

Two representations serve different audiences.

### HarnessProfileConfig (Declarative / File-Friendly)

For YAML/JSON configuration files. Contains only serializable fields:
- `base_system_prompt`, `system_prompt_suffix` (strings)
- `tool_description_overrides` (string-to-string mapping)
- `excluded_tools` (set of strings)
- `excluded_middleware` (set of strings -- name-form only)
- `general_purpose_subagent` (nested dict)

Cannot express `extra_middleware` (runtime-only).

### HarnessProfile (Runtime / Code-Friendly)

For Python code. Contains all fields including:
- `excluded_middleware` (supports both class-form and string-form)
- `extra_middleware` (middleware instances or factories)

### Conversion

```
HarnessProfileConfig  --to_harness_profile()-->  HarnessProfile   (always lossless)
HarnessProfile  --from_harness_profile()-->  HarnessProfileConfig  (raises if extra_middleware populated)
```

Both `register_harness_profile()` accepts either type. `HarnessProfileConfig` is automatically converted at registration time.

---

## 15. Helper Functions in `harness_profiles.py`

### `_scaffolding_violation_label(entry) -> str | None` (line 39)

Lazy-imports `_REQUIRED_MIDDLEWARE_NAMES` from `deepagents.graph` (the set `{"FilesystemMiddleware", "SubAgentMiddleware"}`). For string entries, checks membership. For class entries, checks `entry.__name__` membership. Returns a label string for violations, `None` for allowed entries.

### `_format_scaffolding_rejection(violations) -> str` (line 65)

Formats the error message listing which scaffolding entries were violated. Includes guidance to use `excluded_tools` or adjust profile settings instead of stripping scaffolding.

### `_validate_config_middleware_string(entry, field_name)` (line 864)

Rejects invalid string entries with specific error messages:
- Not a string: `TypeError` with `"{field_name} entries must be strings, got {type}"`
- Empty/whitespace: `ValueError` with `"{field_name} entries must be non-empty, non-whitespace strings"`
- Contains colon: `ValueError` with guidance that class-path entries are not supported
- Starts with underscore: `ValueError` explaining private middleware names are not in the public exclusion surface

### `_serialize_runtime_excluded_middleware_entry(entry) -> str` (line 909)

String entries pass through unchanged. Class entries require a `serialized_name` attribute; raises `ValueError` otherwise with guidance to add `serialized_name: ClassVar[str]` or exclude by `.name` instead.

---

## 16. Defensive Measures

### Immutability

Both profile types use `@dataclass(frozen=True)` plus `__post_init__` hooks that:
- Copy `tool_description_overrides` / `init_kwargs` into `MappingProxyType` (read-only view)
- Copy `extra_middleware` sequences into tuples
- Validate `excluded_middleware` grammar

This prevents both external alias mutation and direct attribute mutation.

### Registry Isolation

The registry stores the `HarnessProfile` / `ProviderProfile` objects directly. Since those objects are frozen dataclasses with read-only views on their mappings, mutation through the registry is impossible.

### Scaffolding Protection

`FilesystemMiddleware` and `SubAgentMiddleware` are protected at two levels:
1. **Construction time**: `__post_init__` checks `_scaffolding_violation_label()` and raises `ValueError` immediately.
2. **Assembly time**: `_validate_excluded_middleware_config()` checks again with the full required-classes/names sets from `deepagents.graph`.

---

## 17. Consumers of the Profile System

| Consumer | File | Usage |
|----------|------|-------|
| `create_deep_agent()` | `graph.py:548-568` | Resolves model via `resolve_model()` (triggers provider profile), then looks up harness profile via `_harness_profile_for_model()` |
| `SubAgent middleware` | `middleware/subagents.py:491` | `resolve_model(spec["model"])` triggers provider profile |
| `Rubric middleware` | `middleware/rubric.py:519` | `resolve_model(self._model)` for grader model |
| `Summarization middleware` | `middleware/summarization.py:1413` | `resolve_model(model)` for summarization model |
| `ConfigurableModelMiddleware` | `deepagents_code/configurable_model.py` | `model_matches_spec()` to decide runtime model swaps |
| `Talon runtime` | `talon/deepagents_talon/runtime.py:813` | `apply_provider_profile()` directly for env-derived overrides |

---

## 18. Knowledge Verification Questions

1. **Q**: A user registers a `HarnessProfile` under `"openai"` with `system_prompt_suffix="Use tools."` and another under `"openai:gpt-5.4"` with `excluded_tools=frozenset({"execute"})`. When `_get_harness_profile("openai:gpt-5.4")` is called, what does the resolved profile contain?
   **A**: The exact-model and provider profiles are merged. The resolved profile has `system_prompt_suffix="Use tools."` (inherited from base since exact did not set it) and `excluded_tools=frozenset({"execute"})` (from exact). All other fields are at their defaults.

2. **Q**: What happens if a third-party plugin's registration callable raises `TypeError` during bootstrap?
   **A**: The exception is logged at `ERROR`, a `warnings.warn()` is emitted, and the plugin is skipped. Other plugins and built-in registrations are unaffected. The bootstrap continues.

3. **Q**: Why does `_merge_middleware` return a factory closure instead of a resolved list?
   **A**: Because both the base and override middleware may themselves be factories (zero-arg callables). The factory closure defers resolution of both sides to lookup time, ensuring fresh instances when needed.

4. **Q**: What is the difference between `_loaded` and `_loading_thread_id` in the bootstrap?
   **A**: `_loaded` is a permanent flag set to `True` after successful bootstrap -- all subsequent calls short-circuit. `_loading_thread_id` is a transient marker identifying which thread is currently performing the bootstrap -- it enables re-entrant calls from the same thread while blocking other threads.

5. **Q**: Why does `HarnessProfileConfig.from_harness_profile()` raise when `extra_middleware` is populated?
   **A**: Because `extra_middleware` contains middleware instances or factories that cannot be serialized to YAML/JSON. Rather than silently dropping them, the function raises to alert the caller that the round-trip would be lossy.

6. **Q**: A profile sets `excluded_middleware=frozenset({"_PrivateMiddleware"})`. What happens?
   **A**: `ValueError` is raised at construction time by `_validate_config_middleware_string()` because underscore-prefixed names refer to private middleware classes not part of the public exclusion surface.

7. **Q**: How does `apply_provider_profile()` compose kwargs when `init_kwargs`, `init_kwargs_factory`, and caller kwargs all set the same key?
   **A**: Precedence is: caller kwargs > factory output > `init_kwargs`. The function builds a dict starting from `init_kwargs`, updates with factory output (factory wins over static), then updates with caller kwargs (caller wins over everything).

8. **Q**: What is `_BOOTSTRAP_HARNESS_KEYS` used for?
   **A**: It is a frozen snapshot of all harness profile keys present in the registry immediately after bootstrap completes. `_has_any_harness_profile()` subtracts this set from the live registry to determine if the user has registered any profiles beyond the built-in defaults. This controls logging verbosity: a "no match" miss with only default profiles stays at `DEBUG`; with user-registered profiles, it escalates to `WARNING`.

9. **Q**: Why does the bootstrap restore registries in-place (`.clear()` + `.update()`) on failure instead of reassigning?
   **A**: Other modules hold direct references to the `_HARNESS_PROFILES` and `_PROVIDER_PROFILES` dict objects. Reassigning would leave those references pointing at the new (restored) dicts, while the old references would still point at the partially populated ones. In-place restore ensures all references see the restored state.

10. **Q**: A user registers `HarnessProfile(excluded_middleware=frozenset({SomeMiddleware}))`, but `SomeMiddleware` is not present in any assembled stack. What happens?
    **A**: `_verify_excluded_middleware_coverage()` raises `ValueError` at agent assembly time, reporting that the exclusion entry matched no middleware. This catches typos and stale profiles. The error message suggests using class-form exclusion to catch typos at import time.
