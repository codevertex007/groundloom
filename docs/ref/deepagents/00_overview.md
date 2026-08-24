# Document 00 -- Deep Agents Framework Overview

## What Is Deep Agents?

Deep Agents is an open-source, batteries-included agent harness built on top of LangGraph by LangChain. It provides an opinionated, production-ready foundation for building and running autonomous AI agents that can plan multi-step work, manage their own context, delegate to sub-agents, read and write files, execute shell commands, and persist memory across sessions -- all out of the box.

The project is explicitly inspired by Claude Code. Its stated goal is to identify what makes Claude Code general-purpose and push that further -- while remaining model-agnostic, extensible, and open. The framework is licensed under the MIT License.

Deep Agents is a Python monorepo containing 7 independently versioned packages (plus 5 partner integration packages) that collectively span the full lifecycle of an AI agent: from the core SDK and graph runtime, through an interactive terminal interface and deployment tooling, to evaluation harnesses and multi-channel runtimes.

---

## Position in the LangChain Ecosystem

Deep Agents sits at the top of a three-layer stack within the LangChain ecosystem. Understanding this layering is essential for knowing when to use each tool and how they compose.

### Layer 1: LangGraph (Graph Runtime)

LangGraph is the low-level graph runtime. It provides the primitives for building stateful, multi-step agent workflows: nodes, edges, conditional branching, streaming, persistence, and checkpointing. When the agent loop itself is not the right shape -- when you need a custom graph topology -- you drop to LangGraph directly.

### Layer 2: LangChain `create_agent` (Minimal Harness)

LangChain's `create_agent` function is a minimal agent harness built on top of LangGraph. It provides a simple tool-calling loop: the model proposes tool calls, the framework executes them, and the results feed back. It is intentionally lightweight -- no opinions about filesystem access, context management, or delegation.

### Layer 3: Deep Agents (Full Harness)

Deep Agents is a more opinionated harness built on top of `create_agent`. It uses the same building blocks as the lower layers but bundles in filesystem operations, sub-agent delegation, context management, skills, persistent memory, and human-in-the-loop approval. The key insight is that these layers compose: any LangGraph `CompiledStateGraph` can be passed in as a sub-agent to a Deep Agent, so custom orchestration plugs in alongside the harness's defaults.

```
+---------------------------------------------+
|           Deep Agents (Harness)              |
|  Filesystem, Sub-agents, Context, Skills,   |
|  Memory, Human-in-the-loop, Tools           |
+---------------------------------------------+
|        LangChain create_agent                |
|  Minimal tool-calling loop                   |
+---------------------------------------------+
|           LangGraph (Runtime)                |
|  Graph, Streaming, Persistence,              |
|  Checkpointing, State Management             |
+---------------------------------------------+
```

For tracing, evaluation, and monitoring in production, the stack integrates with LangSmith.

---

## Monorepo Structure

The repository is organized as a Python monorepo managed with `uv` (replacing pip/poetry for environment and dependency management). Each package is independently versioned using release-please automation with Conventional Commits. The packages share common tooling: `ruff` for linting and formatting, `ty` for static type checking, and `pytest` for testing.

```
deepagents/
├── libs/
│   ├── deepagents/          # Core SDK (deepagents)
│   ├── code/                # Terminal/TUI interface (deepagents-code)
│   ├── cli/                 # CLI deployment tool (deepagents-cli)
│   ├── acp/                 # Agent Context Protocol (deepagents-acp)
│   ├── talon/               # Multi-channel runtime (deepagents-talon)
│   ├── evals/               # Evaluation framework (deepagents-evals)
│   └── partners/            # Partner integration packages
│       ├── daytona/         # langchain-daytona
│       ├── modal/           # langchain-modal
│       ├── quickjs/         # langchain-quickjs
│       ├── runloop/         # langchain-runloop
│       └── vercel/          # langchain-vercel-sandbox
├── examples/                # Working agents and patterns
├── .github/                 # CI/CD workflows and templates
├── AGENTS.md                # Development guidelines
├── LICENSE                  # MIT License
├── README.md                # Project overview
└── release-please-config.json
```

All packages require Python >= 3.11 (with the exception of `deepagents-evals`, which requires >= 3.12). All packages are licensed under the MIT License.

---

## Package Descriptions

### 1. `deepagents` -- Core SDK

- **Location:** `libs/deepagents/`
- **Version:** 0.6.12
- **Python:** >= 3.11, < 4.0
- **Build system:** setuptools

This is the foundational library upon which all other packages depend. It provides the core agent framework including the graph definition, backend abstractions, middleware pipeline, and profile system. The `create_deep_agent` factory function is the primary entry point for constructing agents programmatically.

**Core dependencies:**

| Dependency | Version | Purpose |
|---|---|---|
| `langchain-core` | >= 1.5.0, < 2.0.0 | Base abstractions (messages, tools, runnables) |
| `langsmith` | >= 0.10.9 | Tracing, evaluation, monitoring |
| `langchain-anthropic` | >= 1.5.2, < 2.0.0 | Anthropic model provider |
| `langchain-google-genai` | >= 4.3.1, < 5.0.0 | Google Generative AI model provider |
| `langchain` | >= 1.3.14, < 2.0.0 | Agent construction, chains |
| `wcmatch` | >= 11.0 | Advanced glob/wildcard matching for filesystem operations |

**Optional extras:**

- `quickjs` -- JavaScript REPL middleware via `langchain-quickjs`
- `aws` -- Amazon Bedrock model support via `langchain-aws`
- `video` -- video-frame extraction for `read_file` (via `av`, `pillow`)

**Quickstart:**

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="openai:gpt-5.5",
    tools=[my_custom_tool],
    system_prompt="You are a research assistant.",
)
result = agent.invoke({"messages": "Research LangGraph and write a summary"})
```

The agent can plan, read/write files, and manage its own context. You can add custom tools, swap models, customize prompts, configure sub-agents, and more.

### 2. `deepagents-code` -- Terminal/TUI Interface

- **Location:** `libs/code/`
- **Version:** 0.1.17
- **Python:** >= 3.11, < 4.0
- **Build system:** hatchling
- **Entry points:** `deepagents-code`, `dcode`

This is the pre-built interactive coding agent for the terminal -- analogous to Claude Code or Cursor, but powered by any LLM. It provides a full Textual-based TUI (Terminal User Interface) with file operations, shell access, sub-agent capabilities, slash commands, MCP server integration, and Agent Context Protocol support.

**Installation:**

```bash
curl -LsSf https://langch.in/dcode | bash
```

**Key dependency groups:**

- **Runtime core:** `deepagents==0.7.0b2` (exact pin), LangGraph checkpoint/runtime packages, `httpx`, `textual` (TUI framework), `rich` (terminal rendering), `prompt-toolkit`
- **Default model providers:** `langchain-anthropic`, `langchain-google-genai`, `langchain-openai`
- **Optional model providers (15+):** Baseten, Bedrock, Cohere, DeepSeek, Fireworks, Groq, HuggingFace, IBM, LiteLLM, Mistral, NVIDIA, Ollama, OpenRouter, Perplexity, Together, Vertex, xAI
- **Optional sandbox providers (5):** AgentCore, Daytona, Modal, RunLoop, Vercel
- **Utilities:** `tavily-python` (web search), `pillow` (image handling), `pyperclip` (clipboard), `langchain-mcp-adapters`, `deepagents-acp`

The `deepagents-code` package has the largest dependency footprint of any package in the monorepo due to its role as the full-featured end-user application.

### 3. `deepagents-cli` -- CLI Deployment Tool

- **Location:** `libs/cli/`
- **Version:** 0.2.2
- **Python:** >= 3.11, < 4.0
- **Build system:** hatchling
- **Entry points:** `deepagents`, `deepagents-cli`

The CLI package provides deployment tooling for Deep Agents. It contains three subcommands:

- **`init`** -- Scaffold a new Deep Agents project
- **`dev`** -- Run `langgraph dev` against a bundled project for local development
- **`deploy`** -- Deploy an agent to LangGraph Platform via `langgraph deploy`

Note: bare `deepagents` invocations (without a subcommand) print a deprecation notice pointing at `deepagents-code` and exit non-zero. The interactive REPL that previously lived in `libs/cli/` was extracted to `libs/code/` as of `deepagents-cli==0.1.0`.

**Internal layout:**

- `deepagents_cli/main.py` -- argparse wiring and `cli_main` dispatch
- `deepagents_cli/deploy/` -- The entire deploy/dev/init pipeline (`commands.py`, `bundler.py`, `config.py`, `templates.py`, `context_hub.py`, `frontend_dist/`)

### 4. `deepagents-acp` -- Agent Context Protocol Server

- **Location:** `libs/acp/`
- **Version:** 0.0.8
- **Python:** >= 3.11
- **Build system:** hatchling

This package integrates Deep Agents with the Agent Context Protocol (ACP), enabling structured communication between agents and external systems. It depends on the `agent-client-protocol` library.

### 5. `deepagents-talon` -- Multi-Channel Agent Runtime

- **Location:** `libs/talon/`
- **Version:** 0.0.1 (experimental, Alpha status)
- **Python:** >= 3.11
- **Build system:** hatchling
- **Entry point:** `deepagents-talon`

Talon is a local runtime host for long-running Deep Agents channels and schedules. It supports multiple communication channels including WhatsApp integration, cron-based scheduling, and fleet management for coordinating multiple agent instances. It depends on both `deepagents` and `deepagents-code`.

**Optional extras:**

- `speech` -- Speech processing capabilities via `librosa`, `torch`, `torchaudio`, `transformers`, and `phonemizer`

### 6. `deepagents-evals` -- Evaluation Framework

- **Location:** `libs/evals/`
- **Version:** 0.0.1
- **Python:** >= 3.12, < 3.14 (narrower than other packages)
- **Build system:** setuptools
- **Entry point:** `deepagents-evals`
- **Platform restriction:** macOS arm64 or Linux x86_64 only

The evaluation framework provides a comprehensive suite for benchmarking and evaluating Deep Agents. It integrates with Harbor for sandboxed evaluation environments and LangSmith for feedback and tracing. Features include radar chart visualization, trial runners, and support for 12 model providers for cross-model evaluation.

The package vendors data from the upstream [tau-bench](https://github.com/sierra-research/tau-bench) project for airline domain evaluations. These vendored files must remain byte-identical to upstream.

**Optional extras:**

- `charts` -- Visualization via `matplotlib`

### 7. Partner Packages

The partner packages in `libs/partners/` provide sandbox and middleware integrations. Each wraps a single third-party SDK alongside the core `deepagents` package.

| Package | Version | Third-Party SDK | Purpose |
|---|---|---|---|
| `langchain-daytona` | 0.0.7 | `daytona` | Daytona sandbox integration |
| `langchain-modal` | 0.0.5 | `modal` | Modal sandbox integration |
| `langchain-quickjs` | 0.2.0 | `quickjs-rs` | JavaScript REPL middleware |
| `langchain-runloop` | 0.0.6 | `runloop-api-client` | RunLoop sandbox integration |
| `langchain-vercel-sandbox` | 0.0.1 | `vercel` | Vercel Sandbox integration |

All partner packages pin `deepagents >= 0.6.8, < 0.7.0` and require Python >= 3.11, < 4.0.

---

## How the Packages Relate

The dependency graph flows from the core SDK outward:

```
                      deepagents (core SDK)
                     /    |    \       \     \
                    /     |     \       \     \
    deepagents-code  deepagents-cli  deepagents-acp  partners/*
         |                                    |
    deepagents-talon                          |
         |                                    |
    deepagents-evals  <-- depends on both deepagents and deepagents-code
```

- **`deepagents`** is the dependency root. Every other package depends on it.
- **`deepagents-code`** depends on `deepagents` (exact pin to `0.7.0b2`) and `deepagents-acp`.
- **`deepagents-cli`** depends on `deepagents` (>= 0.6.8).
- **`deepagents-talon`** depends on both `deepagents` and `deepagents-code`.
- **`deepagents-evals`** depends on both `deepagents` and `deepagents-code`.
- **Partner packages** depend only on `deepagents` and their respective third-party SDK.

---

## Key Principles

### Opinionated

Deep Agents ships with defaults tuned for long-horizon, multi-step work. Unlike minimal agent frameworks that leave every decision to the developer, Deep Agents makes deliberate choices about how context is managed, how tasks are delegated, how files are handled, and how the agent loop operates. These defaults are designed to work well out of the box for the common case of complex, autonomous agent tasks.

### Extensible

Every piece of the framework can be overridden or replaced without forking. The middleware pipeline, filesystem backends, model providers, sandbox providers, tools, and sub-agent configurations are all pluggable. A LangGraph `CompiledStateGraph` can be passed in as a sub-agent, meaning custom graph topologies compose with the harness's built-in orchestration. The partner package system demonstrates this extensibility: each sandbox integration is a separate, independently versioned package that plugs into the core SDK's backend abstraction.

### Model-Agnostic

Deep Agents works with any LLM that supports tool calling. This includes:

- **Frontier APIs:** OpenAI, Anthropic, Google
- **Open-weight models on hosted providers:** Baseten, Fireworks, Groq, Together, NVIDIA, and others
- **Self-hosted models:** Ollama, vLLM, llama.cpp

The `deepagents-code` package ships with three default model providers (Anthropic, Google, OpenAI) and offers optional extras for 15+ additional providers. Any LangChain chat model can be used.

### Production-Ready

The framework is built on LangGraph's production infrastructure: streaming, persistence, checkpointing, and state management. It integrates with LangSmith for tracing, evaluation, and monitoring. The `deepagents-cli` package provides deployment tooling for LangGraph Platform. The `deepagents-evals` package provides a formal evaluation framework with Harbor sandbox integration for reproducible benchmarking.

---

## Core Features

### Sub-Agents

Deep Agents can delegate tasks to sub-agents with isolated context windows. This enables divide-and-conquer strategies for complex problems: a parent agent can spawn specialized sub-agents for research, coding, testing, or analysis, each operating within its own context. Any LangGraph `CompiledStateGraph` can serve as a sub-agent, so custom orchestration graphs compose naturally with the harness.

### Filesystem

The framework provides pluggable filesystem access with read, write, edit, and search operations. Filesystem backends can be local, sandboxed, or remote. The five partner sandbox integrations (Daytona, Modal, RunLoop, Vercel, AgentCore) demonstrate the range of supported backends. The core SDK uses `wcmatch` for advanced glob and wildcard matching across filesystem operations.

### Context Management

Long-running agent sessions accumulate large context windows. Deep Agents includes middleware for managing this: summarizing long threads to keep the context focused, and offloading verbose tool outputs to disk to avoid overwhelming the model's context window. This is critical for long-horizon tasks where naive context accumulation would degrade model performance or exceed token limits.

### Shell Access

Agents can execute shell commands in configurable sandbox environments. The choice of sandbox determines the security boundary: local execution, Daytona containers, Modal functions, RunLoop VMs, Vercel sandboxes, or AgentCore environments. The shell tool provides the agent with the ability to install packages, run scripts, compile code, execute tests, and interact with the operating system.

### Persistent Memory

Deep Agents supports pluggable state and store backends for cross-session recall. This means agents can remember context from previous interactions, build up knowledge over time, and maintain continuity across restarts. The `deepagents-code` package uses SQLite-based checkpointing via `langgraph-checkpoint-sqlite` for persistence.

### Human-in-the-Loop

Tool calls can be routed through a human approval step before execution. Users can approve, edit, or reject proposed tool calls, providing a safety mechanism for high-stakes operations. This is particularly important for filesystem writes, shell commands, and other side-effecting operations where the agent's intent should be verified before execution.

### Skills

Skills are reusable behaviors that the agent can load on demand. They provide a mechanism for packaging domain-specific capabilities -- prompt templates, tool configurations, workflows -- into modular units that can be activated as needed. This allows agents to be extended with new capabilities without modifying the core agent configuration.

### Tools

Deep Agents supports two mechanisms for extending agent capabilities with custom tools:

1. **Custom functions:** Bring your own Python functions as tools via the standard LangChain tool interface.
2. **MCP servers:** Connect to any Model Context Protocol server for tool discovery and execution. The `langchain-mcp-adapters` package provides the integration layer.

---

## Security Model: "Trust the LLM"

Deep Agents follows a "trust the LLM" security model. This is a deliberate architectural decision with important implications.

The agent can do anything its tools allow. The framework does not attempt to restrict the model's behavior through prompt engineering or output filtering. Instead, security boundaries are enforced at the tool and sandbox level:

- **Tool-level enforcement:** If the agent should not be able to delete files, do not give it a delete tool. If it should not be able to access the network, do not give it a network tool.
- **Sandbox-level enforcement:** If the agent's shell access should be restricted, run it in a sandboxed environment (Daytona, Modal, RunLoop, etc.) where the sandbox itself enforces the boundary.

The rationale is that LLM self-policing is unreliable. Prompt-based restrictions ("do not delete files") can be bypassed through prompt injection, model confusion, or adversarial inputs. Hardware/software sandboxing and tool-level restrictions are deterministic and enforceable. The security policy states: "Enforce boundaries at the tool/sandbox level, not by expecting the model to self-police."

This model places the burden of security configuration on the deployer, who must carefully consider which tools and sandbox environments are appropriate for their use case.

---

## Development Tooling and Practices

The monorepo uses a consistent set of development tools across all packages:

| Tool | Purpose |
|---|---|
| `uv` | Package installer and resolver (replaces pip/poetry) |
| `make` | Task runner (see per-package Makefiles) |
| `ruff` | Linter and formatter |
| `ty` | Static type checking |
| `pytest` | Testing framework |
| `release-please` | Automated releases via Conventional Commits |

**Key practices:**

- All Python code must include type hints and return types.
- Google-style docstrings with Args sections for all public functions.
- Unit tests in `tests/unit_tests/` (no network calls), integration tests in `tests/integration_tests/`.
- Conventional Commits for PR and commit titles, with required scope.
- Editable installs via `[tool.uv.sources]` for local development.
- Benchmarks via `pytest-codspeed` with 10% regression threshold.

---

## Release and CI/CD

Releases are automated via release-please. When Conventional Commits land on `main`, release-please creates or updates a release PR with version bumps and CHANGELOG entries. Merging the release PR triggers the release pipeline:

```
Build --> Unit tests (against built package) --> Publish to Test PyPI --> Publish to PyPI (OIDC) --> GitHub Release
```

CI enforces:

- PR title linting (Conventional Commits with required scope)
- Release-please parse checking (validates the would-be squash-merge message)
- Automated labeling (size, file, title, contributor tier)
- Per-package change detection for targeted lint/test jobs

---

## Relationship to Claude Code

The README explicitly acknowledges the inspiration: "Inspired by Claude Code: an attempt to identify what makes it general-purpose, and push that further." The `deepagents-code` package is the most direct manifestation of this -- it is an interactive terminal coding agent with file operations, shell access, sub-agent delegation, slash commands, and MCP server integration, running in a Textual TUI. The key differentiator is model-agnosticism: where Claude Code is tied to Anthropic's models, `deepagents-code` works with any LLM that supports tool calling.

---

## Resources

- **Documentation:** https://docs.langchain.com/oss/python/deepagents/overview
- **Deep Agents Code docs:** https://docs.langchain.com/deepagents-code
- **API reference:** https://reference.langchain.com/python/deepagents/
- **Examples:** `examples/` directory in the repository
- **Community forum:** https://forum.langchain.com/c/oss-product-help-lc-and-lg/deep-agents/18
- **LangChain ecosystem overview:** https://docs.langchain.com/oss/python/concepts/products
- **LangChain Academy:** https://academy.langchain.com/
- **Contributing guide:** https://docs.langchain.com/oss/python/contributing/overview

---

## Document Index

This documentation set consists of 32 documents organized by topic, from high-level overview through implementation details. Each document focuses on a single subsystem and includes source file paths, class/function signatures, configuration options, and cross-references.

### Foundations (00-05)

| Doc | Title | Focus |
|-----|-------|-------|
| [00_overview.md](./00_overview.md) | Framework Overview | This document -- project scope, packages, architecture |
| [01_big_picture.md](./01_big_picture.md) | Big Picture | End-to-end architecture, data flow, design decisions |
| [02_quickstart.md](./02_quickstart.md) | Quickstart | Installation, first agent, basic patterns |
| [03_concepts.md](./03_concepts.md) | Core Concepts | Key abstractions and mental model |
| [04_codebase_map.md](./04_codebase_map.md) | Codebase Map | Directory structure, file inventory |
| [05_dependencies.md](./05_dependencies.md) | Dependencies | Package dependencies and version constraints |

### Core SDK (06-10)

| Doc | Title | Focus |
|-----|-------|-------|
| [06_graph.md](./06_graph.md) | Graph | `create_deep_agent`, StateGraph, node/edge topology |
| [07_state.md](./07_state.md) | State | `DeepAgentState`, channels, `PrivateStateAttr` |
| [08_tools.md](./08_tools.md) | Tools | Tool registration, filesystem tools, shell tools |
| [09_messages_reducer.md](./09_messages_reducer.md) | Messages Reducer | `_messages_delta_reducer`, `DeltaChannel` |
| [10_backends.md](./10_backends.md) | Backends | `BackendProtocol`, filesystem, shell, sandbox, composite |

### Middleware (11-19)

| Doc | Title | Focus |
|-----|-------|-------|
| [11_middleware_overview.md](./11_middleware_overview.md) | Middleware Overview | Pipeline ordering, hook protocol, required middleware |
| [12_filesystem_middleware.md](./12_filesystem_middleware.md) | Filesystem Middleware | `FilesystemMiddleware`, `PatchToolCallsMiddleware` |
| [13_summarization_middleware.md](./13_summarization_middleware.md) | Summarization | Context compaction, overflow handling, tool truncation |
| [11_middleware_overview.md](./11_middleware_overview.md) | Middleware overview | Middleware stack, skills and progressive disclosure references |
| [15_permissions_middleware.md](./15_permissions_middleware.md) | Permissions / HITL | `HumanInTheLoopMiddleware`, `interrupt_on` configuration |
| [16_tool_exclusion_middleware.md](./16_tool_exclusion_middleware.md) | Tool Exclusion | `_ToolExclusionMiddleware`, profile-driven tool filtering |
| [17_subagents.md](./17_subagents.md) | Subagents | `SubAgentMiddleware`, sync/async subagents, task tool |
| [18_memory.md](./18_memory.md) | Memory | `MemoryMiddleware`, AGENTS.md discovery, context injection |
| [27_evals.md](./27_evals.md) | Evaluation | Evaluation, grading, and regression guidance |

### Configuration and Profiles (20-22)

| Doc | Title | Focus |
|-----|-------|-------|
| [20_profiles.md](./20_profiles.md) | Profiles | `HarnessProfile`, `ProviderProfile`, registration |
| [21_models.md](./21_models.md) | Model Resolution | `resolve_model`, provider aliases, model matching |
| [22_excluded_middleware.md](./22_excluded_middleware.md) | Excluded Middleware | Profile-driven middleware exclusion, `_REQUIRED_MIDDLEWARE` |

### Deployment Surfaces (23-27)

| Doc | Title | Focus |
|-----|-------|-------|
| [23_acp_server.md](./23_acp_server.md) | ACP Server | `deepagents-acp`, Agent Communication Protocol |
| [24_cli_deploy.md](./24_cli_deploy.md) | CLI Deploy | `deepagents-cli`, LangGraph Platform deployment |
| [25_code_agent.md](./25_code_agent.md) | Code Agent | `deepagents-code`, Textual TUI, slash commands |
| [26_talon.md](./26_talon.md) | Talon | Multi-channel runtime, WhatsApp, cron scheduling |
| [27_evals.md](./27_evals.md) | Evals | Evaluation framework, Harbor sandbox, benchmarks |

### Architecture and Reference (28-30, Appendix)

| Doc | Title | Focus |
|-----|-------|-------|
| [28_execution_flows.md](./28_execution_flows.md) | Execution Flows | Step-by-step runtime traces for key scenarios |
| [29_architecture.md](./29_architecture.md) | Architecture | Cross-cutting concerns, design patterns, trade-offs |
| [30_reimplementation_guide.md](./30_reimplementation_guide.md) | Reimplementation Guide | What you would need to rebuild from scratch |
| [25_code_agent.md](./25_code_agent.md) | Code-agent architecture | Dedicated architecture guidance for the code-agent runtime |

---

## Summary

Deep Agents occupies a specific and well-defined niche in the LangChain ecosystem: it is the opinionated, batteries-included agent harness that sits above LangGraph and LangChain's `create_agent`. It provides the full set of capabilities needed for autonomous, long-horizon agent work -- filesystem access, sub-agent delegation, context management, shell execution, persistent memory, human-in-the-loop approval, skills, and extensible tooling -- while remaining model-agnostic and production-ready.

The monorepo structure reflects a clear separation of concerns: the core SDK provides the framework, `deepagents-code` provides the end-user terminal application, `deepagents-cli` provides deployment tooling, partner packages provide sandbox integrations, `deepagents-acp` provides protocol interoperability, `deepagents-talon` provides multi-channel runtime capabilities, and `deepagents-evals` provides the evaluation infrastructure. Each package is independently versioned and can be adopted individually or composed together.
