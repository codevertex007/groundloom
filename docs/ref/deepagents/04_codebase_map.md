# Codebase Map

This document provides a comprehensive map of the Deep Agents monorepo. It describes the purpose of each major directory, the role of each package, and how the packages relate to one another. Use this as a navigational reference when exploring the codebase or onboarding new contributors.

---

## Repository Root

```
deepagents/
├── .github/
├── docs/
├── examples/
├── libs/
│   ├── deepagents/       # Core SDK
│   ├── code/             # Terminal interface
│   ├── cli/              # Deployment CLI
│   ├── acp/              # ACP server
│   ├── talon/            # Multi-channel runtime
│   ├── evals/            # Evaluation framework
│   └── partners/         # Sandbox integrations
├── AGENTS.md
├── README.md
├── action.yml
└── release-please-config.json
```

The repository follows a monorepo layout managed with release-please for versioning. All publishable packages live under `libs/`. The root contains project-wide configuration, CI/CD definitions, documentation, and example projects.

---

## Top-Level Directories

### `.github/`

Contains GitHub-specific configuration: CI/CD workflow definitions, issue and pull request templates, and automation scripts. Workflows handle testing, linting, building, and releasing each package independently.

### `docs/`

Project-wide documentation that is not tied to any single package. Includes architecture overviews, onboarding guides, and reference material such as this codebase map.

### `examples/`

A collection of 17 standalone example projects demonstrating how to use the Deep Agents SDK and related packages. Each example is self-contained and shows a specific use case or integration pattern. These serve as both learning resources and integration tests.

### `AGENTS.md`

Development guidelines and conventions for the project. This file defines coding standards, commit message formats, review expectations, and architectural principles that contributors should follow.

### `README.md`

The project overview and entry point for newcomers. Covers what Deep Agents is, how to install it, and where to find more detailed documentation.

### `action.yml`

A GitHub Action definition that allows external repositories to use Deep Agents as a step in their own CI/CD workflows.

### `release-please-config.json`

Configuration for the release-please tool, which automates versioning and changelog generation across all packages in the monorepo. Each package can be released independently with its own version number.

---

## Package Directory: `libs/`

All publishable Python packages live under `libs/`. Each package has its own `pyproject.toml`, source directory, and test suite. The packages form a layered architecture where the Core SDK sits at the foundation and higher-level packages build on top of it.

---

### `libs/deepagents/` -- Core SDK (v0.6.12)

**Package name:** `deepagents`

This is the foundational package. It defines the agent graph, built-in tools, model configuration, message handling, backend abstractions, middleware pipeline, and configuration profiles. Every other package in the monorepo either depends on or interacts with this SDK.

#### Source Layout

```
deepagents/
├── __init__.py              # Public API exports
├── graph.py                 # create_deep_agent() and agent graph construction
├── _tools.py                # Built-in tool definitions
├── _models.py               # Model configuration and provider abstractions
├── _messages_reducer.py     # Custom messages reducer for state management
├── _excluded_middleware.py   # Middleware exclusion logic
├── _version.py              # Package version constant
├── _api/                    # API deprecation helpers and compatibility shims
├── backends/                # Execution layer (10 modules)
├── middleware/               # Processing pipeline (16 modules)
└── profiles/                # Configuration presets
```

#### Key Entry Point: `graph.py`

The `create_deep_agent()` function is the primary public API. It constructs a LangGraph-based agent graph by assembling backends, middleware, tools, and model configuration into a runnable agent. This is what downstream consumers call to instantiate an agent.

#### Backends (`backends/`)

The backends directory contains 10 modules that define the execution layer -- the actual capabilities an agent can use to interact with the outside world.

| Module | Purpose |
|--------|---------|
| `protocol.py` | Defines the abstract backend protocol that all backends must implement. This is the contract that ensures interchangeability. |
| `composite.py` | Composes multiple backends together, allowing an agent to use several execution environments simultaneously. |
| `filesystem.py` | File system operations: reading, writing, searching, and navigating files. |
| `local_shell.py` | Local shell command execution for running scripts and system commands. |
| `sandbox.py` | Remote sandbox execution for running code in isolated environments. |
| `langsmith.py` | Integration with LangSmith for tracing, logging, and evaluation. |
| `context_hub.py` | Context management for maintaining and retrieving contextual information during agent execution. |
| `store.py` | Key-value storage backend for persisting data across agent invocations. |
| `state.py` | State management for tracking agent state throughout a session. |
| `utils.py` | Shared utility functions used across multiple backends. |

The `protocol.py` module is especially important because it defines the interface that all backends conform to. The `composite.py` module enables mixing and matching backends, so an agent can have file access, shell execution, and sandbox capabilities all at once.

#### Middleware (`middleware/`)

The middleware directory contains 16 modules that form a processing pipeline. Middleware intercepts and transforms messages, applies policies, manages context windows, and handles tool call processing. Middleware modules are composed in a chain, with each one having the opportunity to inspect and modify the data flowing through the agent.

#### Profiles (`profiles/`)

Configuration presets that bundle together specific combinations of backends, middleware, and settings for common use cases. Profiles simplify agent creation by providing sensible defaults.

#### Tests

Located at `libs/deepagents/tests/`. Contains unit and integration tests for the SDK.

---

### `libs/code/` -- Terminal Interface (v0.1.17)

**Package name:** `deepagents-code`

This is the interactive terminal application that provides a rich text-based user interface for working with Deep Agents. It is the primary way developers interact with the system during development.

#### Source Layout

```
deepagents_code/
├── main.py                 # Application entry point
├── app.py                  # Application lifecycle and initialization
├── agent.py                # Agent integration layer
├── server.py               # Local server for API access
├── widgets/                # 30+ UI widgets (Textual-based)
├── skills/                 # User-extensible skill definitions
├── built_in_skills/        # Pre-packaged skills
├── mcp_providers/          # MCP (Model Context Protocol) server integrations
├── integrations/           # External service integrations
└── (60+ additional modules)
```

#### Architecture

The terminal interface is built on the Textual framework, which provides a modern TUI (Text User Interface) with mouse support, rich text rendering, and responsive layouts. The 30+ widgets in the `widgets/` directory handle everything from message display to file trees to input handling.

The application follows a layered architecture:

1. **`main.py`** handles CLI argument parsing and launches the application.
2. **`app.py`** manages the application lifecycle, screen layout, and event loop.
3. **`agent.py`** bridges the UI to the Core SDK, managing agent sessions and message flow.
4. **`server.py`** runs a local HTTP server that exposes agent capabilities via an API.

#### Skills System

The skills system (`skills/` and `built_in_skills/`) allows both built-in and user-defined capabilities to be surfaced as slash commands in the terminal interface. Built-in skills ship with the package; user skills can be added per-project or globally.

#### MCP Providers

The `mcp_providers/` directory contains integrations with Model Context Protocol servers. MCP allows the agent to connect to external tool providers using a standardized protocol.

#### Relationship to Core SDK

This package pins its dependency on `deepagents==0.7.0b2` (exact version). It uses the Core SDK's `create_deep_agent()` function to instantiate agents and adds the terminal UI, skills system, and MCP integration on top.

---

### `libs/cli/` -- Deployment CLI

**Package name:** `deepagents-cli`

A command-line tool for deploying Deep Agents to production environments. While `deepagents-code` is for interactive development, `deepagents-cli` handles the deployment workflow.

#### Source Layout

```
deepagents_cli/
├── main.py                 # CLI entry point
└── deploy/
    ├── api_client.py       # API communication with deployment targets
    ├── commands.py         # CLI command definitions
    ├── payload.py          # Deployment payload construction
    ├── project.py          # Project configuration parsing
    └── state.py            # Deployment state tracking
```

#### Purpose

The deployment CLI packages an agent project, communicates with a deployment API, and manages deployment state. It reads project configuration, constructs a deployment payload, sends it to the target environment, and tracks the deployment lifecycle.

---

### `libs/acp/` -- ACP Server

**Package name:** `deepagents-acp`

An implementation of the Agent Communication Protocol (ACP) server. ACP provides a standardized interface for external systems to communicate with Deep Agents over HTTP.

#### Source Layout

```
deepagents_acp/
├── server.py               # ACP server implementation
└── utils.py                # Server utility functions
```

#### Purpose

The ACP server exposes agent capabilities through a well-defined protocol, enabling integration with other agent frameworks and orchestration systems. It handles request routing, message serialization, and session management.

---

### `libs/talon/` -- Multi-Channel Runtime

**Package name:** `deepagents-talon`

A runtime for deploying agents across multiple communication channels. Talon enables a single agent to be accessible via different interfaces such as WhatsApp, with built-in scheduling and media handling.

#### Source Layout

```
deepagents_talon/
├── runtime.py              # Core runtime engine
├── host.py                 # Host process management
├── fleet.py                # Multi-agent fleet coordination
├── channels/
│   └── whatsapp/           # WhatsApp channel integration
├── cron/
│   ├── scheduler.py        # Job scheduling engine
│   ├── jobs.py             # Job definitions
│   └── tools.py            # Scheduling-related tools
├── config/                 # Runtime configuration
├── media/                  # Media handling (images, audio, documents)
├── speech/                 # Speech-to-text and text-to-speech
└── observability/          # Monitoring and logging
```

#### Architecture

Talon follows a host-fleet-channel architecture:

- **Runtime** (`runtime.py`): The core engine that processes messages and manages agent lifecycle.
- **Host** (`host.py`): Manages the host process, handling startup, shutdown, and health checks.
- **Fleet** (`fleet.py`): Coordinates multiple agent instances, enabling scaling and load distribution.
- **Channels**: Pluggable communication channel adapters. Currently includes WhatsApp, with the architecture supporting additional channels.
- **Cron**: A built-in job scheduler that allows agents to perform actions on a schedule, independent of incoming messages.
- **Media and Speech**: Handle non-text content, enabling agents to process and generate images, audio, and documents.
- **Observability**: Monitoring, metrics, and structured logging for production deployments.

---

### `libs/evals/` -- Evaluation Framework

**Package name:** Not published as a standalone package; used internally for testing and benchmarking.

The evaluation framework provides tools for systematically testing agent performance, generating radar charts of capabilities, and analyzing trial results.

#### Source Layout

```
├── deepagents_evals/
│   ├── cli.py              # Evaluation CLI commands
│   ├── radar.py            # Radar chart generation
│   └── trial_summary.py    # Trial result summarization
├── deepagents_harbor/
│   ├── backend.py          # Evaluation backend
│   ├── deepagents_wrapper.py # Agent wrapping for evaluation
│   ├── failure.py          # Failure classification
│   ├── langsmith.py        # LangSmith integration for eval tracing
│   ├── metadata.py         # Evaluation metadata handling
│   └── stats.py            # Statistical analysis
├── scripts/
│   ├── run_trials.py       # Execute evaluation trials
│   ├── generate_radar.py   # Generate radar visualizations
│   ├── analyze.py          # Analyze evaluation results
│   └── (additional scripts)
└── tests/
    ├── unit_tests/         # Unit tests for eval framework
    └── evals/
        └── tau2_airline/   # Airline domain evaluation suite
```

#### Purpose

The evaluation framework wraps agents in a controlled harness (`deepagents_harbor`), runs them through predefined scenarios, collects metrics, classifies failures, and produces reports. The `tau2_airline` evaluation suite tests agent performance on airline-related customer service scenarios.

The radar chart functionality (`radar.py`, `generate_radar.py`) creates visual representations of agent capabilities across multiple dimensions, making it easy to compare different agent configurations or model providers.

---

### `libs/partners/` -- Sandbox Integrations

Partner-contributed packages that integrate various sandbox and execution environments with the Deep Agents ecosystem. Each sub-directory is an independent package.

#### Sub-packages

| Directory | Package | Purpose |
|-----------|---------|---------|
| `daytona/` | `langchain_daytona` | Integration with Daytona development environments as agent sandboxes. |
| `modal/` | `langchain_modal` | Integration with Modal for serverless sandbox execution. |
| `quickjs/` | `langchain_quickjs` | QuickJS JavaScript engine integration for lightweight code execution. Contains 8 core files. |
| `runloop/` | `langchain_runloop` | Integration with Runloop for managed sandbox environments. |
| `vercel/` | `langchain_vercel_sandbox` | Integration with Vercel's sandbox infrastructure. |

#### Naming Convention

All partner packages follow the `langchain_*` naming pattern, indicating they implement the LangChain tool or backend interface. This ensures they can be used interchangeably through the Core SDK's backend protocol.

---

## Package Dependency Graph

The packages form a layered dependency structure:

```
                    deepagents (Core SDK)
                   /        |         \
                  /         |          \
    deepagents-code    deepagents-cli   deepagents-talon
         |                                    |
    deepagents-acp                       channels, cron
         |
    partner packages (langchain_*)
```

### Dependency Relationships

1. **Core SDK (`deepagents`)** has no internal dependencies on other packages in the monorepo. It depends on LangChain, LangGraph, LangSmith, and model provider libraries (Anthropic, Google). It is the foundation that everything else builds upon.

2. **Terminal Interface (`deepagents-code`)** depends on the Core SDK at an exact pinned version (`deepagents==0.7.0b2`). It also depends on the Textual framework for its UI, multiple LangGraph packages for checkpointing and runtime, and optionally on partner packages for sandbox support and model provider libraries.

3. **Deployment CLI (`deepagents-cli`)** depends on the Core SDK for project configuration parsing and agent construction.

4. **ACP Server (`deepagents-acp`)** provides the Agent Communication Protocol and is consumed by `deepagents-code` as an optional dependency.

5. **Multi-Channel Runtime (`deepagents-talon`)** depends on the Core SDK and adds channel-specific adapters, scheduling, media handling, and fleet management.

6. **Evaluation Framework (`libs/evals/`)** depends on the Core SDK and LangSmith for tracing evaluation runs.

7. **Partner Packages (`libs/partners/`)** implement the backend protocol defined in the Core SDK. They are consumed as optional dependencies by `deepagents-code` and can be used directly with the Core SDK.

### Version Coordination

The monorepo uses release-please to manage versioning. Each package has its own version number and changelog. The Core SDK version is the most critical coordination point: when it changes, `deepagents-code` must update its pinned dependency. Partner packages depend on the backend protocol, which is part of the Core SDK's public API and follows semantic versioning.

---

## Key Source Files Reference

This section lists the most important files that a new contributor should understand first.

### Core SDK

| File | Significance |
|------|-------------|
| `libs/deepagents/deepagents/__init__.py` | Defines the public API surface. Anything not exported here is considered internal. |
| `libs/deepagents/deepagents/graph.py` | The `create_deep_agent()` function -- the primary entry point for creating agents. |
| `libs/deepagents/deepagents/backends/protocol.py` | The abstract backend protocol. Understanding this is essential for writing new backends. |
| `libs/deepagents/deepagents/backends/composite.py` | How multiple backends are composed together. |
| `libs/deepagents/deepagents/_tools.py` | Built-in tool definitions available to all agents. |
| `libs/deepagents/deepagents/_models.py` | Model configuration and provider abstraction. |

### Terminal Interface

| File | Significance |
|------|-------------|
| `libs/code/deepagents_code/main.py` | CLI entry point -- start here to understand how the application launches. |
| `libs/code/deepagents_code/app.py` | Application lifecycle and screen management. |
| `libs/code/deepagents_code/agent.py` | Bridge between the UI and the Core SDK. |

### Deployment CLI

| File | Significance |
|------|-------------|
| `libs/cli/deepagents_cli/main.py` | CLI entry point for deployment commands. |
| `libs/cli/deepagents_cli/deploy/commands.py` | Deployment command definitions. |

---

## Navigating the Codebase

### Finding Where a Feature Lives

- **Agent creation and graph logic**: `libs/deepagents/deepagents/graph.py`
- **Tool definitions**: `libs/deepagents/deepagents/_tools.py`
- **Backend capabilities** (file, shell, sandbox): `libs/deepagents/deepagents/backends/`
- **Message processing pipeline**: `libs/deepagents/deepagents/middleware/`
- **Terminal UI widgets**: `libs/code/deepagents_code/widgets/`
- **Skills (slash commands)**: `libs/code/deepagents_code/skills/` and `built_in_skills/`
- **MCP integrations**: `libs/code/deepagents_code/mcp_providers/`
- **Deployment**: `libs/cli/deepagents_cli/deploy/`
- **Multi-channel delivery**: `libs/talon/deepagents_talon/channels/`
- **Scheduling**: `libs/talon/deepagents_talon/cron/`
- **Evaluation and benchmarking**: `libs/evals/`
- **Sandbox providers**: `libs/partners/`

### Understanding Data Flow

A typical agent interaction follows this path:

1. A user message enters through an interface (terminal UI, ACP server, or a channel like WhatsApp).
2. The interface passes the message to the Core SDK's agent graph.
3. The agent graph runs the message through the middleware pipeline (context management, policy enforcement, tool call processing).
4. The model generates a response, potentially including tool calls.
5. Tool calls are routed to the appropriate backend (filesystem, shell, sandbox).
6. Backend results flow back through the middleware pipeline.
7. The final response is returned to the interface for display or delivery.

This cycle repeats for multi-turn conversations, with state maintained by the LangGraph checkpointing system.
