# Concepts

This document describes the core abstractions that make up the Deep Agents framework. Understanding these concepts is essential for configuring agents effectively, extending the system with custom behavior, and debugging issues when they arise.

---

## 1. Agent Graph

At the heart of every Deep Agents instance is a **LangGraph CompiledStateGraph**. This graph defines the agent loop -- the cyclic process through which the agent receives input, reasons, acts, and produces output.

The agent loop follows this sequence:

1. **Receive input.** The graph receives an initial state containing the user's message and any relevant configuration.
2. **LLM generates a response.** The configured language model processes the current state (messages, system prompt, available tools) and produces a response. This response may be a plain text answer, or it may include one or more tool calls.
3. **Tools execute.** If the LLM response contains tool calls, the graph routes to the tool execution node. Each tool call is dispatched to the appropriate tool function, and the results are collected.
4. **Results fed back.** Tool results are appended to the message history and the graph loops back to the LLM node for another round of reasoning.
5. **Repeat until done.** Steps 2 through 4 repeat until the LLM produces a response with no tool calls, signaling that the task is complete (or until an exit condition such as a maximum iteration count is reached).

This loop is not hardcoded -- it is a compiled LangGraph graph, which means it can be inspected, visualized, and extended using standard LangGraph APIs. The graph structure also enables features like checkpointing (saving and resuming mid-execution) and streaming (observing each step as it happens).

The graph is the outermost orchestration layer. Everything else -- state, backends, middleware, tools -- plugs into this graph to define what the agent can do and how it behaves.

---

## 2. State (DeepAgentState)

The agent graph operates on a structured state object defined as a **TypedDict** called `DeepAgentState`. This state is the single source of truth for everything the agent knows and has done during a session.

The base `DeepAgentState` TypedDict defines exactly **one** field:

- **messages**: The conversation history, including user messages, assistant responses, and tool call/result pairs. This field uses a **custom messages reducer** (`_messages_delta_reducer`, wrapped in a `DeltaChannel`) that handles merging and ordering of messages as the graph executes, while keeping checkpoint growth linear.

All other state is contributed by **middleware** as they are added to the stack (each middleware may declare its own `state_schema`). For example:

- **files**: contributed by `FilesystemMiddleware` \u2014 a representation of the files the agent has read or modified, so it need not re-read the filesystem every turn.
- **memory contents**: contributed by `MemoryMiddleware` (a `PrivateStateAttr` channel) \u2014 the loaded `AGENTS.md` content.

There is **no** `memory` or `configuration` field on the base state; runtime
configuration is carried by the per-run `context` (a `context_schema`), not by
`DeepAgentState`.

The state is passed through every node in the graph. Each node can read from the state, produce updates, and those updates are merged back using the appropriate reducers. This functional approach (state in, updates out) makes the agent loop predictable and testable.

---

## 3. Backends

Backends are the **execution layer** of Deep Agents. They provide the actual capabilities that tools and middleware rely on -- file I/O, shell execution, sandboxed environments, persistent storage, and more.

### The Backend Protocol

Backends are defined by a **protocol** (specified in `protocol.py`). Any object that satisfies the protocol can serve as a backend, making the system extensible without inheritance hierarchies. The protocol defines the interface that all backends must implement, ensuring consistent behavior regardless of the underlying implementation.

### Backend Types

The framework includes several backend implementations, each providing a distinct set of capabilities:

- **filesystem**: Provides file read/write operations. This is the backend that powers the agent's ability to read source code, create new files, and modify existing ones. It operates on the local filesystem by default.

- **local_shell**: Executes shell commands on the host machine. When the agent needs to run a build, execute tests, or interact with command-line tools, the local_shell backend handles the subprocess management, output capture, and error reporting.

- **sandbox**: A restricted execution environment that isolates the agent's operations. Useful when running untrusted code or when you want to prevent the agent from making uncontrolled changes to the host system.

- **composite**: Combines multiple backends into a single unified interface. This allows the agent to access file operations, shell execution, and other capabilities through one backend object, with requests routed to the appropriate underlying backend based on the operation type.

- **langsmith**: Integrates with LangSmith for tracing, monitoring, and debugging agent runs. When enabled, this backend records detailed execution traces that can be viewed in the LangSmith dashboard.

- **context_hub**: Manages contextual information that the agent can reference during execution. This backend handles loading, indexing, and retrieving context from various sources.

- **store**: Provides key-value storage for persistent data. Used by the memory system and other components that need to persist information across sessions or agent invocations.

- **state**: Manages internal agent state that is not part of the primary conversation flow. This backend handles auxiliary state tracking that sits alongside the main `DeepAgentState`.

Backends are composable. A typical agent configuration layers several backends together -- a filesystem backend for file operations, a local_shell backend for command execution, and a store backend for persistence -- all wrapped in a composite backend that presents a unified interface to the rest of the system.

---

## 4. Middleware

Middleware forms the **processing pipeline** of the agent. Each middleware component wraps or transforms some aspect of the agent's behavior, adding capabilities, enforcing constraints, or modifying the flow of data through the system.

Middleware is applied in a defined order, and each piece can:

- Modify the state before it reaches the LLM (pre-processing).
- Modify the LLM's response before tools are executed (interception).
- Modify tool results before they are fed back to the LLM (post-processing).
- Short-circuit the loop entirely (for example, to block a tool call that lacks permission).

### Public Middleware

These middleware components represent the primary extension points for customizing agent behavior:

- **filesystem**: Manages file-related state, ensuring the agent's view of the filesystem stays consistent across turns. Handles file tracking, diffing, and synchronization with the filesystem backend.

- **memory**: Enables persistent recall across sessions. This middleware loads relevant memories at the start of a session and saves new memories as the agent works. It integrates with the store backend for actual persistence.

- **subagents**: Enables the agent to spawn isolated sub-agent instances for delegated tasks. When the agent determines that a subtask is best handled independently, the subagents middleware creates a new agent with its own state, runs it to completion, and returns the result to the parent agent. Sub-agents run synchronously -- the parent agent waits for the sub-agent to finish before continuing.

- **async_subagents**: The asynchronous variant of the subagents middleware. Async sub-agents run concurrently with the parent agent and with each other. The parent agent can continue its own work while sub-agents execute in the background, collecting results when they become available.

- **permissions**: Implements human-in-the-loop approval for tool calls. When enabled, this middleware intercepts tool calls before execution and presents them to the user for approval or rejection. This is critical for safety in environments where the agent has access to destructive operations (file deletion, shell commands, network requests).

- **rubric**: Applies evaluation criteria to the agent's outputs. The rubric middleware can score responses against predefined quality metrics, enabling automated quality assurance in production deployments.

- **skills**: Manages the loading and execution of reusable skill definitions. Skills are pre-packaged behaviors that the agent can activate on demand (see the Skills section below). This middleware handles skill discovery, loading, and integration into the agent's tool set.

- **summarization**: Manages the agent's context window by summarizing older portions of the conversation. When the message history grows too long for the model's context window, this middleware compresses earlier messages into a summary, preserving the essential information while freeing up token budget for new content.

- **patch_tool_calls**: Modifies or corrects tool calls before they are executed. This middleware can fix common formatting issues, normalize parameters, or transform tool calls to match expected schemas.

### Internal Middleware

These middleware components handle low-level concerns and are generally not configured directly by users:

- **_fs_interrupt**: Handles filesystem-related interrupts, such as detecting when a file the agent is working on has been modified externally.

- **_message_eviction**: Removes old messages from the conversation history when it exceeds configured limits. Unlike summarization (which compresses), eviction simply drops messages that are no longer needed, based on age or relevance.

- **_overflow_clip**: A safety net for context window management. If the total token count of the state exceeds the model's context window even after summarization and eviction, overflow clipping truncates content to ensure the LLM call does not fail.

- **_tool_exclusion**: Filters the set of available tools based on the current context. Some tools may only be appropriate in certain phases of execution, and this middleware ensures that the LLM only sees the tools that are currently relevant.

The middleware pipeline is one of the most powerful extension points in Deep Agents. By composing middleware, you can build agents with sophisticated behaviors -- permission-gated filesystem access, automatic context management, memory-augmented reasoning, and more -- without modifying the core agent loop.

---

## 5. Tools

Tools are **functions the agent can call** to interact with the world. When the LLM determines that it needs to take an action (read a file, run a search, execute a command), it emits a tool call, and the agent framework dispatches it to the appropriate tool function.

### Built-in Tools

Deep Agents ships with a set of built-in tools covering common operations:

- **File operations**: Reading, writing, creating, and modifying files on the local filesystem. These tools integrate with the filesystem backend and middleware for consistent state tracking.
- **Shell execution**: Running shell commands and capturing their output. The shell tools integrate with the local_shell backend and can be gated by the permissions middleware.
- **Search**: Searching file contents, directory structures, and other indexed data.

### Custom Tools

You can define custom tools using LangChain's `StructuredTool` class. A custom tool requires:

1. A **function** that implements the tool's logic.
2. A **name** that the LLM uses to reference the tool.
3. A **description** that tells the LLM when and how to use the tool.
4. An **args_schema** (a Pydantic model) that defines the tool's input parameters.

Custom tools are passed to `create_deep_agent` via the `tools` parameter. The agent automatically registers them and makes them available to the LLM alongside the built-in tools.

The tool system is designed for composability. You can mix built-in tools with any number of custom tools, and the LLM will select the appropriate tool for each step based on the tool descriptions and the current task.

---

## 6. Profiles

Profiles are **configuration presets** that bundle together a coherent set of settings for common use cases. Instead of manually configuring the model, system prompt, middleware stack, backend set, and tool list for every agent, you can select a profile that provides sensible defaults for a particular scenario.

A profile might specify:

- Which model to use.
- Which middleware components to enable and in what order.
- Which backends to configure.
- What system prompt to apply.
- Which tools to include or exclude.

Profiles are a convenience layer. Everything a profile does can be done through explicit configuration -- profiles simply package common configurations for reuse. You can also use a profile as a starting point and override individual settings as needed.

---

## 7. Sub-agents

Sub-agents are **isolated agent instances** that the parent agent spawns to handle delegated tasks. Sub-agents are a key mechanism for breaking complex work into manageable pieces.

### How Sub-agents Work

When the parent agent encounters a task that is better handled in isolation -- for example, researching a specific topic, generating a code module, or analyzing a dataset -- it can delegate that task to a sub-agent. The sub-agent:

1. Receives its own initial state (typically a description of the delegated task).
2. Runs its own agent loop with its own LLM calls, tool executions, and state management.
3. Returns its final output to the parent agent.

Sub-agents operate in isolation. They have their own message history, their own context window, and their own tool set. This isolation prevents cross-contamination of state and allows each sub-agent to focus entirely on its assigned task.

### Synchronous vs. Asynchronous Sub-agents

Deep Agents supports two sub-agent execution modes:

- **Synchronous sub-agents** (via the `subagents` middleware): The parent agent pauses while the sub-agent runs. The parent resumes only after the sub-agent returns its result. This is simple and predictable but can be slow for tasks that could run in parallel.

- **Asynchronous sub-agents** (via the `async_subagents` middleware): The parent agent continues its own work while sub-agents run concurrently. Multiple async sub-agents can execute simultaneously. The parent collects results as they become available. This is more complex but enables significant speedups for parallelizable work.

Sub-agents can be configured with different models, tools, and system prompts than the parent agent. This allows you to use a smaller, faster model for simple subtasks and reserve larger, more capable models for complex reasoning.

---

## 8. Skills

Skills are **reusable behaviors** that the agent can load on demand. A skill packages a specific capability -- a set of instructions, tools, and workflows -- into a discrete unit that can be activated when needed.

Skills differ from tools in scope: a tool is a single function call, while a skill may encompass a multi-step workflow involving multiple tool calls, specific prompting strategies, and custom logic. Skills are managed by the `skills` middleware, which handles discovery, loading, and integration.

When a skill is activated, it can:

- Add new tools to the agent's available tool set.
- Modify the system prompt to include skill-specific instructions.
- Define multi-step workflows that the agent follows.

Skills are the primary mechanism for extending an agent's capabilities without modifying its core configuration. They enable a plug-in architecture where new behaviors can be added, shared, and versioned independently.

---

## 9. Memory

Memory gives the agent **persistent cross-session recall**. Without memory, each agent invocation starts with a blank slate -- the agent has no knowledge of previous sessions. The memory system changes this by storing and retrieving information across invocations.

### How Memory Works

The memory system is built on pluggable **store backends**. When the memory middleware is enabled:

1. At the start of a session, the middleware queries the store backend for relevant memories and injects them into the agent's state.
2. During the session, the agent can create new memories (explicitly or through automated extraction).
3. At the end of the session (or periodically during long sessions), new memories are persisted to the store backend.

The store backend determines where memories are actually stored -- in a local file, a database, a cloud service, or any other storage system that implements the store protocol.

### What Gets Remembered

Memory entries can include:

- Facts the agent learned during previous sessions.
- User preferences and recurring instructions.
- Project-specific context (file layouts, conventions, architecture decisions).
- Outcomes of previous tasks (what worked, what failed).

The memory middleware is responsible for deciding which memories are relevant to the current session. It uses the current context (the user's message, the project state, the agent's configuration) to query the store and retrieve the most pertinent entries.

---

## 10. Human-in-the-Loop

The **permissions middleware** implements human-in-the-loop control over agent actions. This is a critical safety mechanism that ensures the agent cannot take destructive or sensitive actions without explicit human approval.

### How It Works

When the permissions middleware is enabled, it intercepts tool calls before they are executed. For each intercepted tool call, the middleware:

1. Presents the tool call to the user, showing the tool name, parameters, and a description of what the tool will do.
2. Waits for the user to approve or reject the call.
3. If approved, the tool call proceeds normally.
4. If rejected, the tool call is blocked and the agent is informed that the action was not permitted.

### Permission Granularity

The permissions middleware supports fine-grained control. You can configure:

- Which tools require approval (some tools may be whitelisted and run without prompting).
- Which tool parameters trigger approval (for example, file writes might be approved automatically for certain directories but require approval for others).
- Default behavior (approve all, reject all, or ask for each).

This system balances autonomy with safety. The agent can work independently on routine tasks while still requiring human sign-off for operations that could have significant consequences.

---

## 11. Context Management

Large language models have finite context windows. Deep Agents includes several mechanisms for managing context, ensuring the agent can handle long conversations and complex tasks without exceeding the model's limits.

### Summarization Middleware

The **summarization middleware** is the primary context management tool. When the conversation history grows beyond a configured threshold, this middleware:

1. Identifies older portions of the conversation that are candidates for compression.
2. Generates a concise summary of those portions, preserving the essential information (key decisions, important facts, task progress).
3. Replaces the original messages with the summary, freeing up token budget for new content.

Summarization is lossy by design -- some detail is sacrificed for brevity. The middleware is tuned to preserve information that is most likely to be needed in future turns (tool results, user instructions, key findings) while compressing or discarding information that is unlikely to be referenced again (verbose tool outputs, exploratory dead ends).

### Message Eviction

The **_message_eviction** middleware provides a more aggressive form of context management. Instead of summarizing, it simply removes messages that exceed configured limits. Eviction is typically used as a secondary mechanism when summarization alone is not sufficient to keep the context within bounds.

Eviction policies can be based on:

- Message age (oldest messages are evicted first).
- Message type (tool results, which tend to be verbose, may be evicted before user messages).
- Configured maximum message counts.

### Overflow Clipping

The **_overflow_clip** middleware is the last line of defense. If the total token count of the state still exceeds the model's context window after summarization and eviction, overflow clipping truncates content to fit. This is a blunt instrument -- it simply cuts content to fit the window -- but it ensures that the LLM call never fails due to context length errors.

### How These Mechanisms Work Together

The three context management mechanisms operate as a layered system:

1. **Summarization** runs first, compressing older messages while preserving meaning.
2. **Message eviction** runs next, dropping messages that are no longer needed.
3. **Overflow clipping** runs last as a safety net, truncating anything that still exceeds the limit.

This layered approach ensures graceful degradation. Under normal conditions, summarization handles context management with minimal information loss. Under heavy load (very long conversations, large tool outputs), eviction and clipping provide additional pressure relief.

---

## Summary of Architecture

The Deep Agents architecture is built on composition. Each layer has a clear responsibility:

| Layer          | Responsibility                                                      |
| -------------- | ------------------------------------------------------------------- |
| Agent Graph    | Orchestrates the agent loop (LLM call, tool dispatch, iteration).   |
| State          | Single source of truth for all agent data.                          |
| Backends       | Provide execution capabilities (file I/O, shell, storage).          |
| Middleware     | Transform and extend agent behavior (permissions, memory, context). |
| Tools          | Individual functions the LLM can call.                              |
| Profiles       | Configuration presets for common use cases.                         |
| Sub-agents     | Isolated agent instances for delegated work.                        |
| Skills         | Reusable multi-step behaviors loaded on demand.                     |
| Memory         | Persistent cross-session recall.                                    |
| Permissions    | Human-in-the-loop approval for sensitive actions.                   |
| Context Mgmt   | Summarization, eviction, and clipping for context windows.          |

These layers are designed to be independently configurable and composable. You can start with a minimal configuration (just a model and a system prompt) and progressively add middleware, backends, tools, and sub-agents as your requirements grow.
