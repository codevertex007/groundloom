# Dependencies

This document provides a comprehensive reference for all dependencies used across the Deep Agents monorepo. It covers runtime dependencies, optional extras, development tooling, and build systems. Understanding the dependency landscape is essential for troubleshooting version conflicts, evaluating security exposure, and planning upgrades.

---

## Table of Contents

1. [Core SDK (deepagents)](#core-sdk-deepagents)
2. [Terminal Interface (deepagents-code)](#terminal-interface-deepagents-code)
3. [Deployment CLI (deepagents-cli)](#deployment-cli-deepagents-cli)
4. [ACP Server (deepagents-acp)](#acp-server-deepagents-acp)
5. [Multi-Channel Runtime (deepagents-talon)](#multi-channel-runtime-deepagents-talon)
6. [Partner Packages](#partner-packages)
7. [Development Tools](#development-tools)
8. [Build Systems](#build-systems)
9. [Version Pinning Strategy](#version-pinning-strategy)

---

## Core SDK (deepagents)

The Core SDK is the foundation of the monorepo. Its dependencies are minimal and carefully constrained to maintain compatibility across the ecosystem.

### Runtime Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `langchain-core` | `>=1.5.0,<2.0.0` | Core LangChain abstractions including base classes for language models, tools, retrievers, and the LCEL (LangChain Expression Language) composition framework. This is the most critical dependency -- it defines the interfaces that all other LangChain packages implement. |
| `langsmith` | `>=0.10.9` | Client library for LangSmith, the observability and evaluation platform. Provides tracing decorators, run tree management, and dataset access for evaluation. Used by the `langsmith.py` backend and the evaluation framework. |
| `langchain-anthropic` | `>=1.5.2,<2.0.0` | Integration with Anthropic's Claude models. Provides the `ChatAnthropic` class and handles Anthropic-specific features such as extended thinking, tool use, and prompt caching. |
| `langchain-google-genai` | `>=4.3.1,<5.0.0` | Integration with Google's Generative AI models (Gemini). Provides the `ChatGoogleGenerativeAI` class and handles Google-specific features. |
| `langchain` | `>=1.3.14,<2.0.0` | The main LangChain framework package. Provides higher-level abstractions, agents, and chains built on top of `langchain-core`. |
| `wcmatch` | `>=11.0` | Advanced glob matching library. Used for file pattern matching in the filesystem backend, supporting extended glob syntax beyond what Python's standard `fnmatch` module provides. |

### Optional Dependencies

| Package | Extra Name | Purpose |
|---------|-----------|---------|
| `langchain-quickjs` | `quickjs` | Enables the QuickJS JavaScript engine backend for lightweight, sandboxed JavaScript execution. This is one of the partner packages (`libs/partners/quickjs/`). |
| `langchain-aws` | `aws` | Amazon Bedrock model support (the `is_bedrock_model` resolution path in `_models.py`). |
| `av`, `pillow` | `video` | Video-frame extraction so `read_file` can return frames from video files (see `middleware/_video.py`). |

### Dependency Philosophy

The Core SDK uses floor-with-ceiling version constraints (`>=X,<Y`) for LangChain ecosystem packages. This ensures compatibility with new patch and minor releases while protecting against breaking changes in major versions. The `langsmith` dependency uses only a floor constraint (`>=0.8.11`) because LangSmith follows a rapid release cadence and maintains strong backward compatibility.

---

## Terminal Interface (deepagents-code)

The terminal interface has the most extensive dependency tree in the monorepo. It combines the Core SDK with a rich TUI framework, multiple model providers, sandbox integrations, and various utility libraries.

### Core Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `deepagents` | `==0.7.0b2` | The Core SDK, pinned to an exact version. This strict pinning ensures that the terminal interface is always tested and released against a known SDK version, preventing unexpected behavior from SDK changes. |
| `langchain` | `>=1.3.9,<2.0.0` | Direct dependency (in addition to being a transitive dependency via `deepagents`). Required for agent construction APIs used by the Code agent. |
| `langchain-openai` | `>=1.3.2,<2.0.0` | Hard runtime dependency -- OpenAI support ships by default, not just as an optional extra. This means basic OpenAI model usage works without installing the `openai` extra. |
| `langsmith[sandbox]` | `>=0.8.15` | LangSmith client with sandbox integration extra. Provides sandbox-aware tracing and evaluation capabilities beyond the base `langsmith` package used by the Core SDK. |

### LangGraph Ecosystem

The terminal interface uses several LangGraph packages for agent execution, state management, and checkpointing.

| Package | Purpose |
|---------|---------|
| `langgraph-checkpoint-sqlite` | SQLite-based checkpointing for persisting agent state between sessions. Enables conversation continuity and session recovery. |
| `langgraph-sdk` | Client SDK for communicating with LangGraph deployments. Used when connecting to remote agent runtimes. |
| `langgraph-cli[inmem]` | Command-line interface for LangGraph with in-memory runtime support. The `inmem` extra includes the in-memory execution engine for local development. |
| `langgraph-runtime-inmem` | In-memory runtime for executing LangGraph graphs without external infrastructure. Used for local development and testing. |

### UI Framework

The terminal interface is built on the Textual framework and augmented with several complementary libraries.

| Package | Purpose |
|---------|---------|
| `textual` | The primary TUI framework. Provides widgets, layout management, CSS-based styling, event handling, and screen management. Powers the entire terminal user interface. |
| `textual-autocomplete` | Adds autocomplete functionality to Textual input widgets. Used for command completion, file path suggestions, and other interactive input scenarios. |
| `textual-speedups` | Optional C-extension accelerators for Textual. Improves rendering performance for complex layouts and rapid screen updates. |
| `prompt-toolkit` | Terminal input handling library. Provides advanced input features such as multi-line editing, syntax highlighting, and key binding management. |
| `rich` | Rich text rendering library (also the rendering engine underlying Textual). Used for formatting agent output, code blocks, tables, and markdown in the terminal. |
| `markdownify` | Converts HTML to Markdown. Used when agent responses or tool outputs contain HTML that needs to be displayed as formatted text in the terminal. |

### Model Provider Extras

The terminal interface supports 20 model providers through optional extras (plus `all-providers` and `all-sandboxes` composite extras for convenience). Installing an extra pulls in the corresponding `langchain-*` integration package.

| Extra Name | Provider | Notes |
|-----------|----------|-------|
| `anthropic` | Anthropic (Claude) | Claude models via the Anthropic API. |
| `baseten` | Baseten | Model inference platform. |
| `bedrock` | AWS Bedrock | AWS-managed model hosting, including Claude, Titan, and others. |
| `cohere` | Cohere | Command and Embed models. |
| `deepseek` | DeepSeek | DeepSeek models. |
| `fireworks` | Fireworks AI | Fast inference for open-source models. |
| `google-genai` | Google Generative AI | Gemini models via Google's API. |
| `groq` | Groq | Hardware-accelerated inference. |
| `huggingface` | Hugging Face | Open-source models via the Hugging Face Hub. |
| `ibm` | IBM watsonx | IBM's enterprise AI platform. |
| `litellm` | LiteLLM | Universal proxy supporting 100+ model providers through a unified interface. |
| `mistralai` | Mistral AI | Mistral and Mixtral models. |
| `nvidia` | NVIDIA NIM | NVIDIA's inference microservices. |
| `ollama` | Ollama | Local model execution for privacy-sensitive deployments. |
| `openai` | OpenAI | GPT models via the OpenAI API. |
| `openrouter` | OpenRouter | Aggregator providing access to multiple model providers. |
| `perplexity` | Perplexity | Search-augmented language models. |
| `together` | Together AI | Open-source model hosting platform. |
| `vertex` | Google Vertex AI | Google's enterprise ML platform. |
| `xai` | xAI | Grok models. |

These extras allow users to install only the model providers they need, keeping the base installation lightweight. The Core SDK's `_models.py` module handles provider abstraction, so switching between providers requires only configuration changes.

### Sandbox Provider Extras

Five sandbox providers are available as optional extras, corresponding to the partner packages in `libs/partners/`.

| Extra Name | Provider | Notes |
|-----------|----------|-------|
| `agentcore` | AgentCore | Managed sandbox infrastructure. |
| `daytona` | Daytona | Development environment sandboxes (`langchain_daytona`). |
| `modal` | Modal | Serverless function execution (`langchain_modal`). |
| `runloop` | Runloop | Managed sandbox environments (`langchain_runloop`). |
| `vercel` | Vercel | Vercel sandbox infrastructure (`langchain_vercel_sandbox`). |

### Tool Integrations

| Package | Purpose |
|---------|---------|
| `tavily-python` | Client for the Tavily search API. Provides web search capabilities to agents, enabling them to find and retrieve current information. |
| `langchain-mcp-adapters` | Adapters for connecting to MCP (Model Context Protocol) servers. Enables agents to use tools exposed by external MCP-compatible tool providers. |

### ACP Integration

| Package | Purpose |
|---------|---------|
| `deepagents-acp` | Agent Communication Protocol server. Enables the terminal interface to expose agent capabilities via ACP, allowing external systems to interact with running agents. |

### Utility Libraries

| Package | Purpose |
|---------|---------|
| `httpx` | Modern async HTTP client. Used for API calls to model providers, tool services, and other HTTP endpoints. Preferred over `requests` for async contexts. |
| `pyperclip` | Cross-platform clipboard access. Enables copy/paste functionality in the terminal interface. |
| `packaging` | Version parsing and comparison utilities. Used for checking compatibility and managing version-dependent behavior. |
| `python-dotenv` | Loads environment variables from `.env` files. Used for local development configuration, especially API keys. |
| `requests` | HTTP client library. Used in synchronous contexts where `httpx` is not needed. |
| `pillow` | Image processing library (PIL fork). Used for handling image inputs and outputs when agents work with visual content. |
| `pyyaml` | YAML parser and emitter. Used for reading configuration files and agent definitions. |
| `aiosqlite` | Async SQLite interface. Used alongside `langgraph-checkpoint-sqlite` for non-blocking database access during checkpointing. |
| `tomli-w` | TOML writer library. Used for generating and modifying `pyproject.toml` and other TOML configuration files. |
| `uuid-utils` | Fast UUID generation. Used for creating unique identifiers for sessions, messages, and tool calls. |

---

## Deployment CLI (deepagents-cli)

The deployment CLI has a focused dependency set centered on API communication and project configuration parsing.

### Key Dependencies

- The Core SDK (`deepagents`) for project configuration and agent construction.
- HTTP libraries for communicating with deployment targets.
- Configuration parsing libraries for reading project files.

The exact dependency list is defined in `libs/cli/pyproject.toml`.

---

## ACP Server (deepagents-acp)

The ACP server package has minimal dependencies:

- The Core SDK for agent functionality.
- An HTTP server framework for handling incoming ACP requests.
- Serialization libraries for the ACP protocol.

The exact dependency list is defined in `libs/acp/pyproject.toml`.

---

## Multi-Channel Runtime (deepagents-talon)

Talon has channel-specific dependencies in addition to the Core SDK:

- **WhatsApp channel**: WhatsApp Business API client libraries.
- **Speech**: Speech-to-text and text-to-speech service clients.
- **Media**: Image and document processing libraries.
- **Scheduling**: APScheduler or similar for the cron subsystem.
- **Observability**: Logging and metrics libraries.

The exact dependency list is defined in `libs/talon/pyproject.toml`.

---

## Partner Packages

Each partner package in `libs/partners/` has its own focused dependency set:

| Package | Key Dependency | Purpose |
|---------|---------------|---------|
| `langchain_daytona` | Daytona SDK | Communication with Daytona workspace APIs. |
| `langchain_modal` | Modal SDK | Serverless function deployment and execution. |
| `langchain_quickjs` | QuickJS bindings | Embedded JavaScript execution engine. |
| `langchain_runloop` | Runloop SDK | Managed sandbox environment access. |
| `langchain_vercel_sandbox` | Vercel SDK | Vercel sandbox provisioning and management. |

All partner packages depend on `langchain-core` for the tool and backend interface definitions.

---

## Development Tools

These tools are used during development but are not runtime dependencies.

### Package Manager: uv

The monorepo uses `uv` as its Python package manager. `uv` provides fast dependency resolution, virtual environment management, and lock file generation. It replaces `pip` and `pip-tools` in the development workflow.

Key `uv` operations in this project:

- `uv sync` -- Install dependencies from the lock file.
- `uv run` -- Execute commands within the project's virtual environment.
- `uv lock` -- Update the dependency lock file after changing `pyproject.toml`.

### Linter and Formatter: ruff

`ruff` is used for both linting and code formatting across the entire monorepo. It replaces `flake8`, `isort`, `black`, and several other tools with a single, fast Rust-based tool.

Configuration is typically in `pyproject.toml` or `ruff.toml` at the repository root, ensuring consistent style across all packages.

### Type Checker: ty

`ty` is used for type checking Python code. It validates type annotations and catches type errors before runtime.

### Test Framework: pytest

The monorepo uses `pytest` as its test framework, augmented with numerous plugins:

| Plugin | Purpose |
|--------|---------|
| `pytest-asyncio` | Support for testing async functions and coroutines. Essential given the heavy use of async in the agent runtime. |
| `pytest-cov` | Code coverage measurement and reporting. |
| `pytest-mock` | Provides the `mocker` fixture for convenient mocking. |
| `pytest-xdist` | Parallel test execution for faster CI runs. |
| `pytest-timeout` | Prevents hung tests from blocking CI indefinitely. |
| Various others | Additional plugins as specified in each package's dev dependencies. |

Tests are organized per-package under `tests/` directories within each `libs/` sub-package.

---

## Build Systems

The monorepo uses two different Python build systems depending on the package:

### setuptools (Core SDK)

The Core SDK (`libs/deepagents/`) uses `setuptools` as its build backend. This is the traditional Python build system and provides broad compatibility with packaging tools and deployment targets.

Configuration is in `libs/deepagents/pyproject.toml` using the `[build-system]` table:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
```

### hatchling (Terminal Interface)

The terminal interface (`libs/code/`) uses `hatchling` as its build backend. Hatchling is a modern, extensible build system that provides features like dynamic versioning and build hooks.

Configuration is in `libs/code/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Why Two Build Systems

The choice of build system reflects the different needs of each package:

- **setuptools** for the Core SDK provides maximum compatibility, since the SDK is consumed by many downstream packages and environments.
- **hatchling** for the terminal interface provides modern build features like dynamic versioning from VCS tags, which is useful for an application that is released frequently.

---

## Version Pinning Strategy

The monorepo follows distinct version pinning strategies depending on the relationship between packages:

### Internal Dependencies (Exact Pinning)

Internal cross-package dependencies use exact version pinning. For example, `deepagents-code` pins `deepagents==0.7.0b2`. This guarantees that the consumer is tested against a specific SDK version and prevents unexpected behavior from SDK changes. When the SDK releases a new version, downstream packages must explicitly update their pin.

### External Dependencies (Floor with Ceiling)

Most external dependencies use floor-with-ceiling constraints like `>=X.Y.Z,<A.0.0`. The floor ensures minimum feature and bugfix requirements are met, while the ceiling (typically the next major version) protects against breaking API changes. This is the standard approach for LangChain ecosystem packages.

### External Dependencies (Floor Only)

Some rapidly-evolving dependencies like `langsmith` use floor-only constraints (`>=0.8.11`). This is appropriate when the dependency maintains strong backward compatibility and breaking changes are rare, even across minor versions.

### Optional Dependencies (Unconstrained or Loosely Constrained)

Optional extras for model providers and sandbox providers are typically loosely constrained or unconstrained, delegating version resolution to the user's environment. This avoids unnecessary version conflicts when users have specific provider SDK versions installed.

---

## Dependency Update Workflow

When updating dependencies in this monorepo:

1. **Edit** the relevant `pyproject.toml` file to change version constraints.
2. **Run** `uv lock` to regenerate the lock file with resolved versions.
3. **Run** `uv sync` to install the updated dependencies locally.
4. **Run** the test suite for the affected package to verify compatibility.
5. **Check** for transitive dependency conflicts across packages if updating a shared dependency like `langchain-core`.

For security updates, use `uv` to check for known vulnerabilities in current dependencies and update to patched versions.
