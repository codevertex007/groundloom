# Document 21 -- Model Resolution

## Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `libs/deepagents/deepagents/_models.py` | ~175 | `resolve_model()`, `get_model_identifier()`, `get_model_provider()`, `model_matches_spec()`, `is_bedrock_model()`, `_PROVIDER_ALIASES`, `_normalize_provider()` |
| `libs/deepagents/deepagents/graph.py` | ~900+ | `_build_default_model()`, `get_default_model()`, model resolution call sites in `create_deep_agent()` |
| `libs/deepagents/deepagents/profiles/provider/provider_profiles.py` | ~455 | `apply_provider_profile()`, `get_provider_profile()`, `ProviderProfile` |

---

## 1. Model String Format

Deep Agents follows the LangChain `provider:model_name` convention for model specs. A model spec is a string with at most one colon separating the provider from the model identifier:

```
provider:model_name
```

Examples:

- `"openai:gpt-5.4"` -- OpenAI's GPT-5.4
- `"anthropic:claude-sonnet-4-6"` -- Anthropic's Claude Sonnet 4.6
- `"openrouter:anthropic/claude-opus-4-7"` -- Claude Opus 4.7 via OpenRouter

The provider portion determines which LangChain chat model integration is used (e.g. `langchain-openai`, `langchain-anthropic`). The model_name portion is forwarded to the provider's constructor as the model identifier.

Bare model names without a provider prefix (e.g. `"gpt-5.4"`, `"claude-sonnet-4-6"`) are also accepted by `init_chat_model`, which infers the provider from the model name prefix. However, explicit `provider:model` specs are preferred because they make profile resolution unambiguous.

---

## 2. The Resolution Pipeline: `resolve_model`

The `resolve_model` function is the primary entry point for turning a model spec into a `BaseChatModel`. Defined at line 23 in `_models.py`.

```python
def resolve_model(model: str | BaseChatModel) -> BaseChatModel:
```

The function's behavior depends on the input type:

**String input**: The spec is passed to `init_chat_model` along with any kwargs composed from the registered `ProviderProfile`. The composition is handled by `apply_provider_profile(spec)`, which:
1. Looks up the `ProviderProfile` for the spec via `get_provider_profile(spec)`.
2. Runs the profile's `pre_init` hook (if present) with the raw spec string.
3. Builds kwargs by merging `init_kwargs` (static) with `init_kwargs_factory()` output (dynamic), with factory winning on key collision.
4. Returns the merged kwargs dict.
5. `resolve_model` spreads these kwargs into `init_chat_model(model, **merged_kwargs)`.

**`BaseChatModel` input**: The model is returned unchanged. No provider profile is applied because the model is already constructed. Harness profile lookup (performed later by `create_deep_agent`) still proceeds using introspection.

### Resolution in `create_deep_agent()` (lines 548-568)

`create_deep_agent` handles three cases:
- `model is None`: Emits a deprecation warning via `warn_deprecated()`, then calls `_build_default_model()` (the private function, not `get_default_model()`, to avoid a double deprecation warning).
- `model` is a string: Calls `resolve_model(model)`.
- `model` is a `BaseChatModel`: Calls `resolve_model(model)` which returns it unchanged.

After resolution, `_harness_profile_for_model(model, _model_spec)` looks up the behavioral configuration (harness profile).

Subagent models (lines 609-610) default to the parent model and also go through `resolve_model()`.

---

## 3. Model Inspection Functions

Two helper functions extract metadata from a resolved `BaseChatModel`. These are used internally by the harness profile system to look up profiles for pre-built models passed to `create_deep_agent` without a string spec.

### `get_model_identifier(model) -> str | None` (lines 47-59)

Extracts the provider-native model identifier (e.g. `"gpt-5.4"`, `"claude-sonnet-4-6"`).

Providers do not agree on a single field name for the identifier. The function:
1. Tries `model.model_name` first (via the internal `_string_attr` helper).
2. Falls back to `model.model`.
3. Returns `None` if neither attribute exists or both are empty strings.

```python
from deepagents._models import get_model_identifier

identifier = get_model_identifier(model)  # e.g. "gpt-5.4"
```

### `get_model_provider(model) -> str | None` (lines 62-106)

Extracts the provider name (e.g. `"openai"`, `"anthropic"`).

Uses the model's `_get_ls_params()` method, which is the LangSmith introspection method that all major LangChain provider integrations implement. The function:
1. Calls `model._get_ls_params()`.
2. Catches `AttributeError`, `TypeError`, and `NotImplementedError`.
3. Validates the return is a `Mapping`.
4. Extracts the `ls_provider` key.
5. Returns `None` on any failure.

When the provider cannot be extracted, a log message is emitted at `INFO` level so users can diagnose "my profile is not applying" scenarios without enabling debug logging.

```python
from deepagents._models import get_model_provider

provider = get_model_provider(model)  # e.g. "openai"
```

### `_string_attr(obj, attr) -> str | None` (lines 169-174)

Internal helper. Returns `getattr(obj, attr, None)` only if the result is a non-empty string; otherwise returns `None`.

---

## 4. Model Matching: `model_matches_spec`

The `model_matches_spec` function determines whether an existing model instance already matches a string spec. Defined at line 109 in `_models.py`.

```python
def model_matches_spec(model: BaseChatModel, spec: str) -> bool:
```

This is used by the runtime to decide whether a model swap is needed (for example, by `ConfigurableModelMiddleware` in `deepagents_code/configurable_model.py`).

### Matching Algorithm

1. Extract the current model's identifier via `get_model_identifier()`. Return `False` if unavailable.
2. If `spec` exactly equals the identifier (bare spec like `"gpt-5"`), return `True`.
3. Partition `spec` on `:` into `(provider, separator, model_name)`.
4. If no `:` found, or `model_name` does not match the current identifier, return `False`.
5. Extract the current model's provider via `get_model_provider()`.
6. If the provider is uninspectable (returns `None`), fall back to identifier-only match and return `True` (with a `DEBUG` log warning that the provider portion was not verified).
7. Otherwise, compare `_normalize_provider(provider) == _normalize_provider(current_provider)`.

### Examples

```python
from deepagents._models import model_matches_spec

# Bare spec -- matches by identifier only
model_matches_spec(openai_model, "gpt-5.4")  # True if identifier is "gpt-5.4"

# Provider-prefixed spec -- matches by both identifier and provider
model_matches_spec(openai_model, "openai:gpt-5.4")  # True

# Wrong provider -- fails
model_matches_spec(openai_model, "anthropic:gpt-5.4")  # False

# Alias normalization -- "azure_openai" normalizes to "azure"
model_matches_spec(azure_model, "azure:gpt-5.4")  # True
```

---

## 5. Provider Normalization and Aliases

Provider comparison is normalized to handle spelling variations across the ecosystem. LangChain specs and LangSmith params sometimes use different names for the same provider.

### `_normalize_provider(provider) -> str` (lines 155-166)

The normalization pipeline:
1. Lowercase the string.
2. Replace hyphens with underscores.
3. Apply `_PROVIDER_ALIASES` mapping.

So `"Azure_OpenAI"` becomes `"azure_openai"` becomes `"azure"`, and `"MistralAI"` becomes `"mistralai"` becomes `"mistral"`.

### `_PROVIDER_ALIASES` (lines 17-20)

```python
_PROVIDER_ALIASES = {
    "azure_openai": "azure",
    "mistralai": "mistral",
}
```

Two aliases. This prevents mismatches like `"Azure-OpenAI"` vs `"azure"` or `"MistralAI"` vs `"mistral"` from reading as different providers during spec matching.

---

## 6. Default Model Behavior

### `_build_default_model()` (graph.py, lines 146-154)

```python
def _build_default_model() -> ChatAnthropic:
    """Construct the default model without emitting a deprecation warning."""
    return ChatAnthropic(model_name="claude-sonnet-4-6")
```

Internal helper. Exists so `create_deep_agent` can build the default model without triggering the `@deprecated` decorator on `get_default_model()`, avoiding a double-warning when `model=None` is passed.

### `get_default_model()` (graph.py, lines 157-185)

```python
@deprecated(
    since="0.5.3",
    removal="1.0.0",
    message=(
        "Relying on the default model is deprecated and will be removed in "
        "deepagents==1.0.0 alongside support for `model=None` in "
        "`create_deep_agent`. Construct your model explicitly "
        "(e.g., `ChatAnthropic(model_name=...)`). See "
        "https://docs.langchain.com/oss/python/deepagents/models"
    ),
    package="deepagents",
)
def get_default_model() -> ChatAnthropic:
    return _build_default_model()
```

Deprecated since 0.5.3. Scheduled for removal in 1.0.0. Emits a `LangChainDeprecationWarning` once per process. Simply delegates to `_build_default_model()`.

### Deprecation in `create_deep_agent()`

When `model=None` is passed to `create_deep_agent`, the function:
1. Emits its own deprecation warning via `warn_deprecated()` (separate from `get_default_model`'s warning).
2. Calls `_build_default_model()` directly (the private function) to avoid triggering a second deprecation warning from `get_default_model`.

This means users see exactly one deprecation warning per process when using the implicit default, not two.

---

## 7. Supported Model Providers

Deep Agents works with any LLM that supports tool calling. Model providers are resolved via LangChain's `init_chat_model`, which maintains the canonical list in `langchain/chat_models/base.py`.

### Provider Table

| # | Provider String | Package | Chat Model Class |
|---|-----------------|---------|------------------|
| 1 | `openai` | `langchain-openai` | `ChatOpenAI` |
| 2 | `anthropic` | `langchain-anthropic` | `ChatAnthropic` |
| 3 | `azure_openai` | `langchain-openai` | `AzureChatOpenAI` |
| 4 | `azure_ai` | `langchain-azure-ai` | `AzureAIChatCompletionsModel` |
| 5 | `cohere` | `langchain-cohere` | `ChatCohere` |
| 6 | `google_vertexai` | `langchain-google-vertexai` | `ChatVertexAI` |
| 7 | `google_genai` | `langchain-google-genai` | `ChatGoogleGenerativeAI` |
| 8 | `fireworks` | `langchain-fireworks` | `ChatFireworks` |
| 9 | `ollama` | `langchain-ollama` (fallback: `langchain-community`) | `ChatOllama` |
| 10 | `together` | `langchain-together` | `ChatTogether` |
| 11 | `mistralai` | `langchain-mistralai` | `ChatMistralAI` |
| 12 | `huggingface` | `langchain-huggingface` | `ChatHuggingFace` |
| 13 | `groq` | `langchain-groq` | `ChatGroq` |
| 14 | `bedrock` | `langchain-aws` | `ChatBedrock` |
| 15 | `bedrock_converse` | `langchain-aws` | `ChatBedrockConverse` |
| 16 | `google_anthropic_vertex` | `langchain-google-vertexai` | `ChatAnthropicVertex` |
| 17 | `deepseek` | `langchain-deepseek` | `ChatDeepSeek` |
| 18 | `nvidia` | `langchain-nvidia-ai-endpoints` | `ChatNVIDIA` |
| 19 | `ibm` | `langchain-ibm` | `ChatWatsonx` |
| 20 | `xai` | `langchain-xai` | `ChatXAI` |
| 21 | `perplexity` | `langchain-perplexity` | `ChatPerplexity` |

Note: The `nvidia` provider (row 18) is handled by `_init_chat_model_helper` but is absent from the `_SUPPORTED_PROVIDERS` set. It works when passed as a `model_provider=` kwarg but may not be auto-inferred from the colon-prefix syntax.

### Auto-Inference Rules

When a bare model name is passed (no `provider:` prefix), `init_chat_model` infers the provider from the model name prefix:

| Model Name Prefix | Inferred Provider |
|--------------------|-------------------|
| `gpt-`, `o1`, `o3` | `openai` |
| `claude` | `anthropic` |
| `command` | `cohere` |
| `accounts/fireworks` | `fireworks` |
| `gemini` | `google_vertexai` |
| `amazon.` | `bedrock` |
| `mistral` | `mistralai` |
| `deepseek` | `deepseek` |
| `grok` | `xai` |
| `sonar` | `perplexity` |

Explicit `provider:model` specs are preferred over auto-inference because they make profile lookup unambiguous.

### Using Unlisted Providers

Any LangChain chat model can be used by passing a pre-built `BaseChatModel` instance directly to `create_deep_agent`, bypassing the string-spec resolution entirely:

```python
from langchain_community.chat_models import SomeCustomModel
from deepagents import create_deep_agent

model = SomeCustomModel(model_name="my-model", api_key="...")
agent = create_deep_agent(model=model, ...)
```

---

## 8. Model-Specific Parameters

Model-specific parameters such as `temperature`, `max_tokens`, `base_url`, and provider-specific options are configured through the `ProviderProfile` system rather than being passed directly to `resolve_model`. The profile composes these parameters into the `init_chat_model` call.

```python
from deepagents.profiles import ProviderProfile, register_provider_profile

# Set temperature and max_tokens for all OpenAI models
register_provider_profile(
    "openai",
    ProviderProfile(init_kwargs={"temperature": 0, "max_tokens": 4096}),
)

# Override temperature for a specific model
register_provider_profile(
    "openai:gpt-5.4",
    ProviderProfile(init_kwargs={"temperature": 0.7}),
)
```

The precedence order for kwargs, from highest to lowest:

1. **Caller-supplied kwargs** -- values passed directly via `apply_provider_profile`'s `kwargs` parameter.
2. **Factory-produced kwargs** -- values from the profile's `init_kwargs_factory`.
3. **Static init_kwargs** -- values from the profile's `init_kwargs`.

Within the profile itself, factory output wins over static kwargs on key collision. When both provider-level and model-level profiles exist, they are merged with the model-level profile winning on shared keys.

### Common Model Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `temperature` | Controls rando0` (deterministic) to `2.0` |
| `max_tokens` | Maximum number of tokens to generate | `4096`, `8192` |
| `base_url` | Override the API endpoint URL | `"https://my-proxy.com/v1"` |
| `api_key` | API key for authentication | Best set via factory from env var |
| `timeout` | Request timeout in seconds | `30`, `60` |
| `use_responses_api` | OpenAI Responses API (OpenAI only) | `True` (built-in default) |

For runtime-derived parameters (such as API keys read from environment variables), use `init_kwargs_factory` rather than `init_kwargs` so the value is resolved at model-construction time rather than at profile-registration time:

```python
import os
from deepagents.profiles import ProviderProfile, register_provider_profile

register_provider_profile(
    "my_provider",
    ProviderProfile(
        init_kwargs_factory=lambda: {
            "aphook runs (e.g. version checks for OpenRouter).
4. Static `init_kwargs` and factory-produced kwargs are merged.
5. The merged kwargs are passed to `init_chat_model` along with the spec.
6. `init_chat_model` returns a configured `BaseChatModel`.

### Phase 2: Harness Configuration (Harness Profile)

After the model is resolved:

1. `_harness_profile_for_model` looks up the `HarnessProfile`.
2. When a string spec was provided, it is used directly for lookup.
3. When a pre-built model was passed, `get_model_identifier` and `get_model_provider` extract the lookup key from the model instance.
4. The profile's prompt, tool, middleware, and subagent settings are applied during agent graph assembly.

### Pre-built Model Considerations

When a pre-built `BaseChatModel` is passed to `create_deep_agent`:

- **Provider profile is skipped** -- the model is already constructed, so `init_kwargs`, `pre_init`, and factory have no effect.
- **Harness profile may not resolve** -- if the model's `_get_ls_params` does not expose a provider, or if the model identifier does not match any registered key, the harness profile lookup falls through to defaults. A warning is logged when the user has registered profiles but none matched.
- **Bare identifiers are not consulted** -- a pre-built model whose identifier happens to coincide with a registered provider key (e.g. a proxy named `"openai"`) will not silently pick up that provider's harness profile. This is a deliberate safety measure.

---

## 10. Consumers of the Model Resolution System

| Consumer | File | Usage |
|----------|------|-------|
| `create_deep_agent()` | `graph.py:548-568` | `resolve_model(model)` for main and subagent models |
| `SubAgent middleware` | `middleware/subagents.py:491` | `resolve_model(spec["model"])` for subagent model construction |
| `Rubric middleware` | `middleware/rubric.py:519` | `resolve_model(self._model)` for grader model |
| `Summarization middleware` | `middleware/summarization.py:1413` | `resolve_model(model)` for summarization model |
| `ConfigurableModelMiddleware` | `deepagents_code/configurable_model.py` | `model_matches_spec(request.model, model)` to decide runtime model swaps |
| `Harness profile lookup` | `profiles/harness/harness_profiles.py:1279` | `get_model_identifier()` + `get_model_provider()` for pre-built models |
| `Talon runtime` | `talon/deepagents_talon/runtime.py:813` | `apply_provider_profile(model)` directly (bypasses `resolve_model`) for env-derived overrides |
| `QuickJS swarm` | `partners/quickjs/langchain_quickjs/_swarm_task.py` | Imports `resolve_model` for task model resolution |

---

## 11. Public vs. Internal API Surface

**Exported from `deepagents/__init__.py`** (public):
- `ProviderProfile`
- `register_provider_profile`

**Not publicly exported** (internal, import from `deepagents._models` directly):
- `resolve_model`
- `get_model_identifier`
- `get_model_provider`
- `model_matches_spec`
- `_PROVIDER_ALIASES`
- `_normalize_provider`
- `_string_attr`

**Not publicly exported** (internal, import from `deepagents.profiles.provider.provider_profiles`):
- `apply_provider_profile`
- `get_provider_profile`

---

## 12. Knowledge Verification Questions

1. **Q**: What happens when `resolve_model` receives a `BaseChatModel` instance instead of a string?
   **A**: The model is returned unchanged. No provider profile is applied. Harness profile lookup proceeds separately during `create_deep_agent`.

2. **Q**: A user calls `resolve_model("openai:gpt-5.4")`. What kwargs does `init_chat_model` receive from the built-in OpenAI profile?
   **A**: `{"use_responses_api": True}` from the built-in `"openai"` provider profile registered in `_openai.py`.

3. **Q**: Why does `get_model_identifier` check `model_name` before `model`?
   **A**: Different LangChain provider packages use different attribute names. `model_name` is the convention used by `ChatAnthropic` and some others; `model` is used by `ChatOpenAI` and others. Checking both ensures broad compatibility.

4. **Q**: How does `model_matches_spec` handle a model whose provider cannot be inspected?
   **A**: It falls back to identifier-only comparison. If the model name from the spec matches the model's identifier, `True` is returned with a `DEBUG` log warning that the provider portion was not verified.

5. **Q**: What is the difference between `_build_default_model()` and `get_default_model()`?
   **A**: `_build_default_model()` is the private implementation that returns `ChatAnthropic(model_name="claude-sonnet-4-6")` without any deprecation warning. `get_default_model()` is the public function decorated with `@deprecated` that emits a `LangChainDeprecationWarning` and then delegates to `_build_default_model()`.

6. **Q**: A user passes `model=None` to `create_deep_agent`. How many deprecation warnings are emitted?
   **A**: Exactly one. `create_deep_agent` emits its own deprecation warning and then calls `_build_default_model()` directly (not `get_default_model()`), avoiding a second warning.

7. **Q**: How are provider aliases applied during spec matching?
   **A**: Both the spec's provider and the model's actual provider are independently normalized via `_normalize_provider()` (lowercase, hyphens to underscores, alias lookup). The normalized forms are compared. So `"azure_openai:gpt-5"` and a model whose LangSmith provider is `"azure"` will match because `_normalize_provider("azure_openai")` returns `"azure"`.

8. **Q**: Can a provider not in the supported list be used?
   **A**: Yes. Pass a pre-built `BaseChatModel` instance directly to `create_deep_agent`. String-spec resolution via `init_chat_model` is limited to the supported providers, but any LangChain-compatible chat model works when pre-constructed.
