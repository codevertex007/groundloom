# Document 22 -- Excluded Middleware

## Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `libs/deepagents/deepagents/_excluded_middleware.py` | ~225 | All four core functions: validate, collision check, apply, verify |
| `libs/deepagents/deepagents/graph.py` | lines 206-233 | `_REQUIRED_MIDDLEWARE`, `_REQUIRED_MIDDLEWARE_CLASSES`, `_REQUIRED_MIDDLEWARE_NAMES` constants; call sites in `create_deep_agent` |
| `libs/deepagents/deepagents/profiles/harness/harness_profiles.py` | various | `HarnessProfile.__post_init__` validation, `_scaffolding_violation_label()`, `_format_scaffolding_rejection()`, `_validate_config_middleware_string()`, `_serialize_runtime_excluded_middleware_entry()` |

---

## 1. What Is Excluded Middleware?

Excluded middleware is a mechanism that allows specific middleware to be dynamically removed from the agent's middleware stack at assembly time. Rather than requiring users to manually construct middleware lists without the unwanted entries, the `excluded_middleware` field on `HarnessProfile` and `HarnessProfileConfig` declares which middleware should be stripped from the fully assembled stack before the agent begins execution.

The excluded middleware system exists because the middleware stack is assembled from multiple sources -- built-in middleware, profile-contributed middleware (via `extra_middleware`), and user-supplied middleware (via the `middleware` parameter on `create_deep_agent`). A profile cannot simply "not include" middleware that another layer adds. It needs a way to subtract entries from the final assembled stack, regardless of which layer introduced them.

---

## 2. The Two Exclusion Forms

`HarnessProfile.excluded_middleware` accepts a `frozenset[type[AgentMiddleware] | str]` -- entries may be either middleware **classes** or **strings**.

### Class-Form Exclusion

```python
from deepagents.middleware import TodoListMiddleware

HarnessProfile(
    excluded_middleware=frozenset({TodoListMiddleware}),
)
```

- Matched by **exact type identity**: `type(mw) is cls`, not `isinstance(mw, cls)`.
- A subclass of an excluded class is NOT removed (see Section 6 for rationale).
- Typos surface at import time -- if the class does not exist, Python raises `ImportError`.
- Preferred when the middleware class is importable.

### String-Form Exclusion

```python
HarnessProfile(
    excluded_middleware=frozenset({"SummarizationMiddleware"}),
)
```

- Matched by **exact `.name` match**: `mw.name == entry`.
- `AgentMiddleware.name` defaults to the class's `__name__` but can be overridden. For example, the private class `_DeepAgentsSummarizationMiddleware` exposes `.name = "SummarizationMiddleware"` as its public alias.
- Required for YAML/JSON-loaded profiles (`HarnessProfileConfig` stores only strings).
- Required for middleware whose class is not part of the public import surface.
- Subject to grammar validation at construction time (see Section 10).
- Subject to name-collision detection at filter time (see Section 7).

### Mixed Sets

Profiles may mix class and string entries freely:

```python
HarnessProfile(
    excluded_middleware=frozenset({
        TodoListMiddleware,              # class form
        "SummarizationMiddleware",       # string form
    }),
)
```

Merged profiles union their exclusion sets, so a base profile using string form and an override using class form compose correctly.

---

## 3. Required Middleware Protection

### Constants in `graph.py` (lines 206-233)

```python
_REQUIRED_MIDDLEWARE: tuple[
    tuple[type[AgentMiddleware[Any, Any, Any]], tuple[str, ...]], ...
] = (
    (FilesystemMiddleware, ()),
    (SubAgentMiddleware, ()),
)
```

Each entry pairs a class with a tuple of extra string aliases beyond `__name__`. Both currently have empty alias tuples `()`, meaning they are only matched by their `__name__` (`"FilesystemMiddleware"`, `"SubAgentMiddleware"`).

```python
_REQUIRED_MIDDLEWARE_CLASSES: frozenset[type[AgentMiddleware[Any, Any, Any]]] = frozenset(
    cls for cls, _ in _REQUIRED_MIDDLEWARE
)
# Result: frozenset({FilesystemMiddleware, SubAgentMiddleware})
```

```python
_REQUIRED_MIDDLEWARE_NAMES: frozenset[str] = frozenset(
    name for cls, aliases in _REQUIRED_MIDDLEWARE
    for name in (cls.__name__, *aliases)
)
# Result: frozenset({"FilesystemMiddleware", "SubAgentMiddleware"})
```

### Why These Are Protected

- **FilesystemMiddleware**: Backs every built-in file tool (Read, Write, Edit, Glob, Grep) and enforces `permissions` rules. Removing it would silently strip the agent of its file-manipulation capabilities and remove the security boundary on file access.
- **SubAgentMiddleware**: Backs the `task` tool handler for subagent dispatch. Removing it would silently disable the subagent system.

### Protection Layers (Defense-in-Depth)

Protection fires at **four** distinct points:

| Layer | Where | What | When |
|-------|-------|------|------|
| 1 | `HarnessProfileConfig.__post_init__` | `_scaffolding_violation_label()` checks each string entry against `_REQUIRED_MIDDLEWARE_NAMES` | Config construction |
| 2 | `HarnessProfile.__post_init__` | `_scaffolding_violation_label()` checks each entry (class or string) against `_REQUIRED_MIDDLEWARE_NAMES` | Profile construction |
| 3 | `_validate_excluded_middleware_config` (Phase 1) | Checks against `required_classes` and `required_names` from `graph.py` | Agent assembly |
| 4 | `_verify_excluded_middleware_coverage` (Phase 3) | Subtracts required sets from unmatched to avoid confusing error messages | Post-assembly |

Layers 1 and 2 fire at object construction, so register-site typos fail fast. Layer 3 fires at assembly time with the authoritative required sets from `graph.py`. Layer 4 is pure defense-in-depth.

---

## 4. The Three-Phase Exclusion Pipeline

The exclusion pipeline runs in three phases during `create_deep_agent` graph assembly. Each phase serves a distinct purpose and catches a different class of error.

### Pipeline Flow

```
                      +------------------------------+
                      |  Profile with                |
                      |  excluded_middleware          |
                      +------------------------------+
                                   |
                                   v
                +--------------------------------------+
                |  Phase 1: VALIDATE                   |
                |  _validate_excluded_middleware_config |
                |  - Reject scaffolding entries         |
                +--------------------------------------+
                    |                       |
                    | scaffolding found     | all valid
                    v                       v
            ValueError               +---------------------------+
            "required scaffolding     |  Phase 2: APPLY           |
             cannot be excluded"      |  _apply_excluded_middleware|
                                      |  (GP subagent stack)      |
                                      +---------------------------+
                                                   |
                                                   v
                                      +---------------------------+
                                      |  Phase 2: APPLY           |
                                      |  _apply_excluded_middleware|
                                      |  (main agent stack)       |
                                      +---------------------------+
                                                   |
                                                   v
                              +--------------------------------------+
                              |  Phase 3: VERIFY                     |
                              |  _verify_excluded_middleware_coverage |
                              |  - Every entry must have matched     |
                              |    something across all stacks       |
                              +--------------------------------------+
                                  |                       |
                                  | unmatched found       | all matched
                                  v                       v
                          ValueError               Assembly continues
                          "entries matched no
                           middleware"
```

### Phase 1: Configuration Validation

**Function**: `_validate_excluded_middleware_config` (lines 23-64 of `_excluded_middleware.py`)

```python
def _validate_excluded_middleware_config(
    profile: HarnessProfile,
    *,
    required_classes: frozenset[type[AgentMiddleware[Any, Any, Any]]],
    required_names: frozenset[str],
) -> None:
```

**Logic:**
1. Early return if `profile.excluded_middleware` is empty or falsy.
2. Partition entries into `excluded_classes` (set of types via `isinstance(entry, type)`) and `excluded_names` (set of strings).
3. Compute `forbidden_classes = excluded_classes & required_classes` and `forbidden_names = excluded_names & required_names`.
4. If either set is non-empty, lazy-import `_format_scaffolding_rejection` from `harness_profiles.py` and build labels: class entries use `cls.__name__`, string entries use `f"{name!r} (string)"`.
5. Raise `ValueError` with the formatted scaffolding rejection message.

**Error message** (from `_format_scaffolding_rejection`, lines 65-79 of `harness_profiles.py`):
```
HarnessProfile.excluded_middleware is invalid:
  - required scaffolding cannot be excluded: <sorted labels>
    (back filesystem tools, subagent dispatch, and permission enforcement --
    use excluded_tools for per-tool visibility or adjust profile settings
    instead of stripping scaffolding)
```

**Why required_classes and required_names are parameters, not hard-coded**: The required-scaffolding set is owned by `deepagents.graph` (the `_REQUIRED_MIDDLEWARE` tuple), not by `_excluded_middleware.py`. Threading them as parameters avoids a circular import (`graph` already imports this module), keeps scaffolding policy next to `create_deep_agent`, and allows testing with mock required sets.

### Phase 2: Stack Filtering

**Function**: `_apply_excluded_middleware` (lines 90-165 of `_excluded_middleware.py`)

```python
def _apply_excluded_middleware(
    stack: list[AgentMiddleware[Any, Any, Any]],
    profile: HarnessProfile,
    *,
    matched_classes: set[type[AgentMiddleware[Any, Any, Any]]] | None = None,
    matched_names: set[str] | None = None,
) -> list[AgentMiddleware[Any, Any, Any]]:
```

**Logic:**
1. If `profile.excluded_middleware` is empty or falsy, return `list(stack)` (always a fresh copy, never the original).
2. Partition exclusions into `excluded_classes` (set of types) and `excluded_names` (set of strings).
3. Initialize `name_matched_types: dict[str, set[type]]` to track which concrete types each string name matched.
4. Iterate through every middleware instance in `stack`:
   - Get `mw_type = type(mw)` and `mw_name = mw.name`.
   - **Class matching**: If `mw_type in excluded_classes` (exact type match using `type()`, NOT `isinstance`), record in `matched_classes` if provided, and skip (drop) the middleware.
   - **Name matching**: If `mw_name in excluded_names` (exact string match against `AgentMiddleware.name`), record in `name_matched_types` dict and `matched_names` if provided, and skip.
   - Otherwise, append to the `filtered` output list.
5. Call `_raise_on_name_collisions(name_matched_types)` to check for ambiguous string matches.
6. If any middleware was removed, log a `DEBUG` message with the removed count, sorted repr of all exclusion entries, sorted class names, and sorted excluded name strings.
7. Return the `filtered` list (always a new list).

**Key design decisions:**
- Class matching uses `type(mw)` not `isinstance()`, so a subclass is preserved when the base class is excluded. This mirrors the `_merge_middleware` slot-identity semantics where type identity, not inheritance, determines matching.
- Class-form is checked **first**. If a middleware matches both a class exclusion and a name exclusion, the class match takes priority (the name branch is never reached).
- `matched_classes` and `matched_names` are optional mutable sets that accumulate across calls. This is critical because a single profile applies to multiple stacks (main agent + GP subagent), and an exclusion entry only needs to match *somewhere* across all stacks, not in every stack. The cross-stack accumulation prevents false negatives in the coverage check (Phase 3).

### Phase 2b: Name Collision Detection

**Function**: `_raise_on_name_collisions` (lines 67-87 of `_excluded_middleware.py`)

```python
def _raise_on_name_collisions(
    name_matched_types: dict[str, set[type[AgentMiddleware[Any, Any, Any]]]],
) -> None:
```

Detects when a single string name matched instances of multiple distinct concrete classes **within a single stack**. This is almost always unintended -- two different middleware classes share the same `.name`, and the string exclusion is inadvertently removing both.

**Error message:**
```
HarnessProfile.excluded_middleware name entry matched multiple distinct middleware
classes within a single stack: 'Analytics' matched ['AnalyticsMiddlewareA',
'AnalyticsMiddlewareB']. Use a class-form exclusion via the runtime `HarnessProfile`
to disambiguate.
```

**Why per-stack, not cross-stack**: A name matching different concrete types in *different* stacks is expected and legitimate (e.g. a custom subagent with its own implementation). A collision within a single stack means one string entry is silently removing two distinct middleware implementations.

### Phase 3: Coverage Verification

**Function**: `_verify_excluded_middleware_coverage` (lines 168-225 of `_excluded_middleware.py`)

```python
def _verify_excluded_middleware_coverage(
    profile: HarnessProfile,
    matched_classes: set[type[AgentMiddleware[Any, Any, Any]]],
    matched_names: set[str],
    *,
    required_classes: frozenset[type[AgentMiddleware[Any, Any, Any]]],
    required_names: frozenset[str],
) -> None:
```

**Logic:**
1. Early return if `profile.excluded_middleware` is empty or falsy.
2. Partition exclusions into `excluded_classes` and `excluded_names`.
3. Compute `unmatched_classes = excluded_classes - matched_classes - required_classes` (subtracting `required_classes` as defense-in-depth since those were already rejected upstream).
4. Compute `unmatched_names = excluded_names - matched_names - required_names`.
5. Filter out private-prefix names: `unmatched_names = {name for name in unmatched_names if not name.startswith("_")}`. Private names are already rejected by the grammar check at `HarnessProfile` construction time; skipping here keeps the error message focused on actionable issues.
6. If both unmatched sets are empty, return.
7. Build sorted labels: class names as `cls.__name__`, string names as `f"{name!r} (string)"`.
8. Raise `ValueError`:
   ```
   HarnessProfile.excluded_middleware entries matched no middleware across any assembled
   stack: <labels>. Typo or stale profile -- every exclusion must correspond to a
   middleware actually present at runtime. (Tip: use class-form exclusion when the class
   is available to catch typos at import time.)
   ```

---

## 5. Call Flow in `create_deep_agent`

The three phases are orchestrated by `create_deep_agent` in `graph.py`. The call flow demonstrates how the mutable accumulator sets thread through multiple stacks.

### Main Agent and GP Subagent (Shared Profile)

```python
# Step 1: Validate the profile's excluded_middleware against scaffolding (lines 571-575)
_validate_excluded_middleware_config(
    _profile,
    required_classes=_REQUIRED_MIDDLEWARE_CLASSES,
    required_names=_REQUIRED_MIDDLEWARE_NAMES,
)

# Step 2: Initialize shared accumulator sets
_main_matched_classes: set[type] = set()
_main_matched_names: set[str] = set()

# Step 3: Build GP subagent stack, apply exclusions (line 717)
gp_filtered = _apply_excluded_middleware(
    gp_middleware,
    _profile,
    matched_classes=_main_matched_classes,
    matched_names=_main_matched_names,
)

# Step 4: Build main agent stack, apply exclusions (line 815)
main_filtered = _apply_excluded_middleware(
    deepagent_middleware,
    _profile,
    matched_classes=_main_matched_classes,
    matched_names=_main_matched_names,
)

# Step 5: Verify coverage across both stacks (line 828)
_verify_excluded_middleware_coverage(
    _profile,
    _main_matched_classes,
    _main_matched_names,
    required_classes=_REQUIRED_MIDDLEWARE_CLASSES,
    required_names=_REQUIRED_MIDDLEWARE_NAMES,
)
```

The key insight is that `_main_matched_classes` and `_main_matched_names` are **shared** between the GP subagent filter call (Step 3) and the main agent filter call (Step 4). An exclusion that only matches in one stack (say, middleware present only in the main stack) still counts as "covered" for the combined verification at Step 5. This prevents false positives where an exclusion is valid for the main stack but legitimately absent from the GP subagent's smaller stack.

### Declarative Subagents (Independent Profiles)

Each declarative subagent gets its own profile, its own matched sets, and its own validate/apply/verify cycle:

```python
for subagent_spec in subagent_specs:
    subagent_profile = ...
    _validate_excluded_middleware_config(subagent_profile, ...)

    sub_matched_classes: set[type] = set()
    sub_matched_names: set[str] = set()

    sub_filtered = _apply_excluded_middleware(
        subagent_middleware, subagent_profile,
        matched_classes=sub_matched_classes,
        matched_names=sub_matched_names,
    )

    _verify_excluded_middleware_coverage(
        subagent_profile, sub_matched_classes, sub_matched_names, ...
    )
```

Each subagent has its **own** accumulator sets and its **own** Phase 3 verification. The main agent's accumulators are not shared with subagent accumulators. Each profile is verified independently.

---

## 6. Why Exact-Type Matching (Not `isinstance`)

The filter uses `type(mw) in excluded_classes` (exact type identity), **not** `isinstance(mw, cls)`. This is a deliberate design choice.

### The Problem `isinstance` Would Cause

Consider a middleware hierarchy:

```python
class BaseAnalyticsMiddleware(AgentMiddleware):
    name = "AnalyticsMiddleware"

class CustomAnalyticsMiddleware(BaseAnalyticsMiddleware):
    name = "CustomAnalyticsMiddleware"
```

If a profile excludes `BaseAnalyticsMiddleware` (class form):

| Matching mode | `BaseAnalyticsMiddleware` instance | `CustomAnalyticsMiddleware` instance |
|--------------|-----------------------------------|-------------------------------------|
| `type(mw) is cls` | Excluded | **Kept** |
| `isinstance(mw, cls)` | Excluded | **Excluded** |

With `isinstance`, excluding the base class would silently remove the subclass too, even though the user only intended to exclude the base.

### Consistency with `_merge_middleware`

The exact-type matching mirrors `_merge_middleware` in `harness_profiles.py`, which also uses type identity as the slot key. Both systems treat `type(instance)` as the identity of a middleware slot:

- **Replacing** a middleware (via `extra_middleware` merge) targets the exact type.
- **Excluding** a middleware targets the exact type.
- A subclass introduced by the caller is a **distinct slot** from its parent class.

### Practical Consequences

1. **User subclass preservation**: A user extending a built-in middleware class keeps their extension even when a profile excludes the built-in.
2. **Plugin safety**: A third-party plugin extending a built-in middleware is not silently removed when a profile targets the built-in.
3. **Refactoring stability**: Exclusion behavior does not change when class hierarchies are refactored.
4. **Predictable testing**: The test for "does this exclusion match?" depends only on the concrete type, not on the full inheritance chain.

---

## 7. Grammar Validation: `_validate_config_middleware_string()` (Lines 864-906 of `harness_profiles.py`)

```python
def _validate_config_middleware_string(entry: object, field_name: str) -> None:
```

Runs at `HarnessProfile` and `HarnessProfileConfig` construction time (`__post_init__`). For `HarnessProfileConfig`, every entry is validated (all entries are strings). For `HarnessProfile`, only string entries are validated (class entries skip this function).

### Checks

| Check | Raises | Error Message | Rationale |
|-------|--------|---------------|-----------|
| `not isinstance(entry, str)` | `TypeError` | `"{field_name} entries must be strings, got {type(entry).__name__} ({entry!r})"` | Only strings accepted |
| `not entry or entry.isspace()` | `ValueError` | `"{field_name} entries must be non-empty, non-whitespace strings"` | Empty/whitespace strings are meaningless |
| `":" in entry` | `ValueError` | `"{field_name} entries must be plain middleware names; class-path (module:Class) entries are not currently supported, got {entry!r}."` | Class-path syntax reserved for future revision |
| `entry.startswith("_")` | `ValueError` | `"{field_name} entry {entry!r} cannot start with '_' (underscore-prefixed names refer to private middleware classes not part of the public exclusion surface)."` | Private middleware not in public exclusion surface |

### Relationship to Phase 1

Grammar validation and scaffolding checks are deliberately separated:
- **Grammar validation** (`_validate_config_middleware_string`) runs at construction time. It checks the shape of the string itself.
- **Scaffolding rejection** (`_validate_excluded_middleware_config`) runs at assembly time. It checks whether the entry names required scaffolding, using the authoritative set from `graph.py`.

Both fire `ValueError`, but at different lifecycle points. Grammar errors surface immediately when a profile is defined. Scaffolding errors surface when the profile is used to build an agent.

---

## 8. `HarnessProfileConfig` vs `HarnessProfile` Exclusion Fields

### `HarnessProfileConfig.excluded_middleware`

```python
excluded_middleware: frozenset[str] = frozenset()
```

- **Type**: `frozenset[str]` -- strings only.
- **Purpose**: On-disk representation for YAML/JSON config files.
- **Validation**: Grammar-checked at construction (`_validate_config_middleware_string`) and scaffolding-checked (`_scaffolding_violation_label`).

### `HarnessProfile.excluded_middleware`

```python
excluded_middleware: frozenset[type[AgentMiddleware] | str] = frozenset()
```

- **Type**: `frozenset[type[AgentMiddleware] | str]` -- classes or strings.
- **Purpose**: Runtime representation used by `create_deep_agent`.
- **Validation**: String entries are grammar-checked; all entries are scaffolding-checked.

### Conversion Between the Two

- **Config to Profile** (`HarnessProfileConfig.to_harness_profile()`): String entries pass through as-is. `excluded_middleware=frozenset(self.excluded_middleware)`.

- **Profile to Config** (`HarnessProfileConfig.from_harness_profile()`): Each entry goes through `_serialize_runtime_excluded_middleware_entry()`. String entries pass through; class entries require a `serialized_name: ClassVar[str]` attribute. Without it, `ValueError` is raised.

---

## 9. Serialization and the `serialized_name` Convention

When converting a runtime `HarnessProfile` back to a declarative `HarnessProfileConfig` (via `HarnessProfileConfig.from_harness_profile`), class-form exclusion entries must be serialized to strings. This is handled by `_serialize_runtime_excluded_middleware_entry(entry)` (lines 909-932 of `harness_profiles.py`).

**String entries**: Pass through unchanged.

**Class entries**: Require a `serialized_name: ClassVar[str]` attribute. If the attribute is absent, the function raises `ValueError`:
```
HarnessProfileConfig.from_harness_profile() cannot serialize `excluded_middleware` class
{entry.__name__!r}: it has no public `serialized_name` alias, and arbitrary class-path
serialization is not currently supported. Either add a `serialized_name: ClassVar[str]`
to the class for stable round-trips, or exclude it by `.name` instead.
```

The convention for middleware authors:
- Set `serialized_name` on classes whose `__name__` differs from the public alias users would type.
- Ensure the instance's `.name` property returns the same alias, so string-form exclusion matches at runtime.
- This keeps config-file round-trips stable even when the implementation class is renamed or relocated.

---

## 10. Profile Merge Behavior

When two `HarnessProfile` instances are merged (e.g., a base profile and a model-specific override), their `excluded_middleware` sets are **unioned**:

```python
excluded_middleware=base.excluded_middleware | override.excluded_middleware,
```

This means:
- If the base profile excludes `TodoListMiddleware` and the override excludes `SummarizationMiddleware`, the merged profile excludes both.
- Duplicate entries (same class or same string) naturally deduplicate via set union.
- Mixed class/string sets are allowed and preserved.

---

## 11. Use Cases for Middleware Exclusion

### Disabling Summarization for Large-Context Models

Models with very large context windows may not benefit from summarization middleware:

```python
register_harness_profile(
    "my_provider:large-context-model",
    HarnessProfile(
        excluded_middleware=frozenset({"SummarizationMiddleware"}),
    ),
)
```

### Removing Provider-Specific Middleware

Some middleware is only useful for specific providers. An OpenAI model inheriting a profile with Anthropic-specific middleware can strip it:

```python
register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfile(
        excluded_middleware=frozenset({"AnthropicPromptCachingMiddleware"}),
    ),
)
```

### Stripping Middleware for Testing

During development or testing, excluding specific middleware can simplify the agent's behavior:

```python
from deepagents.profiles import HarnessProfile

test_profile = HarnessProfile(
    excluded_middleware=frozenset({"SummarizationMiddleware", "TodoMiddleware"}),
)
```

### YAML-Driven Configuration

For deployments where profile configuration is managed via config files:

```yaml
# profiles/lean-agent.yaml
excluded_middleware:
  - SummarizationMiddleware
  - TodoMiddleware
excluded_tools:
  - execute
```

```python
import yaml
from deepagents.profiles import HarnessProfileConfig, register_harness_profile

with open("profiles/lean-agent.yaml") as f:
    config = HarnessProfileConfig.from_dict(yaml.safe_load(f))

register_harness_profile("openai:gpt-5.4", config)
```

---

## 12. Alternatives to Middleware Exclusion

The error messages from the scaffolding protection system guide users toward alternative mechanisms:

| Goal | Mechanism | Notes |
|------|-----------|-------|
| Hide specific tools from the model | `excluded_tools` field on `HarnessProfile` | Removes tools from the model's view without removing the middleware that provides them |
| Disable the `task` tool entirely | `general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)` and pass no synchronous subagents via `subagents=` | Removes the GP subagent without stripping SubAgentMiddleware |
| Remove file tools selectively | `excluded_tools=frozenset({"write", "edit"})` | Keeps read-only file tools while hiding write tools |
| Customize tool descriptions | `tool_description_overrides` field on `HarnessProfile` | Changes what the model sees in tool descriptions without removing middleware |

---

## 13. Error Messages Summary

| Condition | Phase | Error Type | Message Pattern |
|-----------|-------|-----------|-----------------|
| String entry is empty/whitespace | Construction | `ValueError` | "entries must be non-empty, non-whitespace strings" |
| String entry contains `:` | Construction | `ValueError` | "class-path entries are not currently supported" |
| String entry starts with `_` | Construction | `ValueError` | "cannot start with '_'" |
| Entry is not a string (in config) | Construction | `TypeError` | "entries must be strings, got {type}" |
| Entry names required scaffolding | Construction + Phase 1 | `ValueError` | "required scaffolding cannot be excluded: {names}" |
| String exclusion matched multiple classes in one stack | Phase 2 | `ValueError` | "name entry matched multiple distinct middleware classes" |
| Entry matched nothing across all stacks | Phase 3 | `ValueError` | "entries matched no middleware across any assembled stack" |

All pipeline errors are `ValueError` because they represent invalid profile configuration, not programming errors (which would use `TypeError`).

---

## 14. Helper Functions

### `_scaffolding_violation_label(entry) -> str | None` (line 39 of `harness_profiles.py`)

Lazy-imports `_REQUIRED_MIDDLEWARE_NAMES` from `deepagents.graph`. For string entries, checks membership. For class entries, checks `entry.__name__` membership. Returns a descriptive label for violations, `None` for allowed entries. Used at `HarnessProfile` and `HarnessProfileConfig` construction time.

The lazy import avoids a top-level circular import. By the time any `HarnessProfile` is constructed, `graph.py` is loadable.

### `_format_scaffolding_rejection(violations) -> str` (line 65 of `harness_profiles.py`)

Formats the error message listing which scaffolding entries were violated. Shared between the construction-time check (`HarnessProfile.__post_init__`) and the assembly-time check (`_validate_excluded_middleware_config`), so users see the same wording regardless of where the rejection fires.

### `_serialize_runtime_excluded_middleware_entry(entry) -> str` (line 909 of `harness_profiles.py`)

Converts a runtime `excluded_middleware` entry (which may be a class) back to the string form needed by `HarnessProfileConfig`. String entries pass through; class entries require `serialized_name`.

---

## 15. Knowledge Verification Questions

1. **Q**: Why does `_apply_excluded_middleware` use `type(mw)` instead of `isinstance(mw, cls)` for class matching?
   **A**: To mirror `_merge_middleware` slot-identity semantics. A subclass introduced by the caller is preserved when the profile excludes the base class. This prevents a broad base-class exclusion from unexpectedly removing specialized subclass middleware.

2. **Q**: A profile excludes `{"SummarizationMiddleware"}` by string. `SummarizationMiddleware` is only present in the main agent stack, not the GP subagent stack. Does `_verify_excluded_middleware_coverage` raise?
   **A**: No. The `matched_names` set is shared between both filter calls (GP subagent and main agent). The match in the main agent stack records `"SummarizationMiddleware"` in the shared set, so it is not unmatched when coverage is verified.

3. **Q**: What happens if two different middleware classes in the same stack both have `.name == "MyMiddleware"` and the profile excludes `{"MyMiddleware"}`?
   **A**: `_raise_on_name_collisions` raises `ValueError` because the string name matched instances of multiple distinct concrete classes. The error directs the user to use class-form exclusion to disambiguate.

4. **Q**: Can `FilesystemMiddleware` be excluded using a string exclusion entry?
   **A**: No. The exclusion is rejected at `HarnessProfile` construction time by `_scaffolding_violation_label()`, which checks string entries against `_REQUIRED_MIDDLEWARE_NAMES`. Even if it somehow bypassed construction, `_validate_excluded_middleware_config` at assembly time would catch it as defense-in-depth.

5. **Q**: A profile has `excluded_middleware=frozenset({"NonExistentMiddleware"})`. At what point does the error surface?
   **A**: At agent assembly time, during Phase 3. `_verify_excluded_middleware_coverage` finds that `"NonExistentMiddleware"` did not match any middleware in any assembled stack (main or GP subagent) and raises `ValueError` with a message identifying the unmatched entry and suggesting class-form exclusion for import-time typo detection.

6. **Q**: Why does `_verify_excluded_middleware_coverage` filter out private-prefix names (starting with `_`)?
   **A**: Because private names are already rejected by `_validate_config_middleware_string` at `HarnessProfile` construction time. If a private name somehow reaches coverage verification, filtering it out keeps the error message focused on actionable issues rather than repeating a validation that should have fired earlier.

7. **Q**: What is the return type of `_apply_excluded_middleware` when `profile.excluded_middleware` is empty?
   **A**: It returns `list(stack)` -- always a fresh copy of the input stack, never the original list. This ensures the caller can safely mutate the returned list without affecting the original stack.

8. **Q**: Why does `_apply_excluded_middleware` always return a new list, even when no middleware is excluded?
   **A**: Defensive programming. The caller may append, remove, or reorder elements in the returned list. Returning the original would allow unintended mutation of the shared stack object, which could cause subtle bugs when the same stack is used for multiple agents.

9. **Q**: A middleware class has `serialized_name = "PublicName"` but its `.name` property returns `"DifferentName"`. What breaks?
   **A**: Config-file round-tripping becomes inconsistent. `from_harness_profile` serializes the class as `"PublicName"`, but at runtime, `_apply_excluded_middleware` matches against `.name` which returns `"DifferentName"`. The exclusion would fail to match, and `_verify_excluded_middleware_coverage` would raise `ValueError`.

10. **Q**: How many times does `_validate_excluded_middleware_config` run for a single `create_deep_agent` call with one main agent and two declarative subagents?
    **A**: Three times -- once for the main agent's profile and once for each declarative subagent's profile. The GP subagent shares the main agent's profile and does not trigger a separate validation call.

11. **Q**: What is the priority when a middleware matches both a class exclusion and a name exclusion?
    **A**: The class-form check runs first in the filter loop. If `type(mw) in excluded_classes` is true, the middleware is dropped and the name check is never reached. The match is recorded only in `matched_classes`, not in `matched_names`. This means if the only reason a name entry would have matched is because it also matched by class, the name entry may appear as "unmatched" in Phase 3 -- unless another middleware instance in some stack matches the name without also matching the class.

12. **Q**: Why are `required_classes` and `required_names` parameters rather than module-level constants in `_excluded_middleware.py`?
    **A**: To avoid a circular import. `graph.py` imports `_excluded_middleware.py` and also defines the required sets. If `_excluded_middleware.py` imported back from `graph.py` at module level, a circular dependency would result. Threading as parameters keeps the dependency one-directional and places scaffolding policy ownership in `graph.py`, next to `create_deep_agent`.
