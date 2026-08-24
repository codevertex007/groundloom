# Document 23 -- ACP Server

## What Is ACP?

The **Agent Communication Protocol (ACP)** is a standardized interface between an editor host and an agent backend. It defines how sessions are created, how user prompts flow into the agent, how the agent streams responses back, and how the host requests human-in-the-loop approval for dangerous operations. The protocol is transport-agnostic -- the same agent logic works over stdio, local sockets, or HTTP -- and it is the mechanism that lets Deep Agents run inside editors such as Zed.

The `deepagents-acp` package bridges the Deep Agents SDK with ACP. It lives in `libs/acp/` and contains three source files plus a small test harness.

| Attribute         | Value                                  |
|-------------------|----------------------------------------|
| Package name      | `deepagents-acp`                       |
| Python            | >= 3.11                                |
| Key dependency    | `agent-client-protocol >= 0.10.1`      |
| Source location   | `libs/acp/`                            |
| Entry point       | `deepagents_acp/__main__.py`           |

---

## Package Layout

```
libs/acp/deepagents_acp/
    __init__.py          # Package docstring
    __main__.py          # asyncio entry point for standalone testing
    server.py            # AgentServerACP -- the main server class (~1,038 lines)
    utils.py             # Content converters, shell safety, display helpers (~384 lines)
```

The `__main__.py` module calls `asyncio.run(_serve_test_agent())` -- a convenience function defined at the bottom of `server.py` that wires up a `CompositeBackend` and launches the ACP runtime with a demo agent graph. This is useful for local testing without an editor.

---

## Core Class: `AgentServerACP`

`AgentServerACP` extends the ACP library's `ACPAgent` base class. It wraps a compiled Deep Agent graph (a LangGraph `CompiledStateGraph`; see [06_graph.md](./06_graph.md)) and translates between the ACP protocol surface and the LangGraph execution model.

### Constructor

The constructor accepts either a pre-compiled graph or a **factory function** that produces one. The factory pattern is useful when graph construction depends on runtime context (e.g., a per-session sandbox backend):

```python
from deepagents_acp.server import AgentServerACP

# Pre-compiled graph
server = AgentServerACP(agent=compiled_graph)

# Factory function -- called once per session
server = AgentServerACP(agent=lambda ctx: build_agent_for(ctx))
```

The server is then handed to the ACP runtime, which manages transport (stdio, HTTP, etc.) on behalf of the editor host.

### Lifecycle Methods

| Method                | When Called                        | Responsibility                                                       |
|-----------------------|------------------------------------|----------------------------------------------------------------------|
| `initialize()`        | ACP host boot                      | One-time setup. Currently a no-op placeholder.                       |
| `new_session()`       | Editor opens a new conversation    | Creates a fresh thread ID, initializes session state, returns the ID.|
| `set_session_mode()`  | Editor switches interaction mode   | Updates `_session_modes[session_id]` for mode-aware prompt assembly. |
| `set_config_option()` | Editor pushes a config change      | Applies runtime overrides -- model name, parameters, etc.            |
| `prompt()`            | User sends a message               | Passes input to the graph, streams tokens, handles interrupts.       |
| `cancel()`            | User or editor aborts a run        | Cancels the in-flight LangGraph invocation for a given session.      |

---

## Session Management

Each editor tab or conversation maps to one **session**. The `AgentSessionContext` dataclass tracks per-session state:

```python
@dataclass
class AgentSessionContext:
    cwd: str          # Working directory for the session
    mode: str         # Interaction mode (e.g., "normal", "code-review")
    model: str        # Active model name
```

The server maintains parallel dictionaries keyed by session ID for modes, models, plans, working directories, MCP server configs, and allowed command types. Sessions persist for the lifetime of the editor connection. The server serializes concurrent requests within a session through LangGraph's checkpoint history. For details on how the state graph manages checkpoints, see [07_state.md](./07_state.md).

---

## The Prompt Flow

When `prompt()` is called, the server executes this sequence:

1. **Assemble the input.** The user's text is wrapped in a `HumanMessage` and combined with any pending interrupt state from a prior turn.

2. **Invoke the graph.** The compiled Deep Agent graph is invoked with `astream_events()`, which yields incremental events as the model generates tokens, calls tools, and produces results.

3. **Stream content blocks.** Each event is translated into an ACP content block:
   - **Text tokens** -- incremental AI response text.
   - **Tool call starts** -- the agent is about to invoke a tool.
   - **Tool results** -- the output of a completed tool invocation.

4. **Detect interrupts.** If the graph raises an interrupt (because a tool requires human approval), the stream pauses and a permission request is sent to the editor.

5. **Handle the interrupt response.** The editor sends back the user's decision (approve, reject, or approve-always). The server resumes or rejects the tool call accordingly.

6. **Return the final response.** Once the graph finishes, the server sends a terminal content block and closes the stream.

### Tool Call Display Mapping

Tool calls are mapped to display categories so editors can render them with appropriate icons:

| Internal Tool Name | Display Kind |
|--------------------|--------------|
| `read_file`        | `read`       |
| `edit_file`        | `edit`       |
| `write_file`       | `write`      |
| `execute`          | `execute`    |
| `web_search`       | `search`     |
| `fetch_url`        | `fetch`      |
| `task`             | `task`       |

For the full list of built-in tools available to the agent, see [08_tools.md](./08_tools.md).

---

## Human-in-the-Loop (HITL) Approval

The ACP server implements human-in-the-loop for potentially dangerous operations. When the Deep Agent graph raises a LangGraph interrupt -- typically before executing a shell command, writing a file, or performing a web search -- the server pauses execution and requests approval from the editor.

### Interrupt Handling

The `_handle_interrupts()` method inspects the pending interrupt from the LangGraph checkpoint and constructs an ACP permission request containing the tool name, arguments, a formatted display string (truncated for readability), and the tool category.

### User Response Options

| Response          | Server Behavior                                                    |
|-------------------|--------------------------------------------------------------------|
| **Approve**       | Resumes the graph with the tool call allowed.                      |
| **Reject**        | Resumes the graph with a rejection error; the agent may retry.     |
| **Approve always**| Adds the tool's command type to `_allowed_command_types` for the   |
|                   | session, then resumes. Future calls of the same type skip approval.|

### Auto-Approval Logic

When a tool call arrives and the user has previously selected "approve always" for that command type, the server checks `_allowed_command_types` and auto-approves without sending a permission request. The command type extraction in `utils.py` handles compound shell commands by parsing operators (`&&`, `||`, `;`, `|`) and special handlers for `python`, `node`, `npm`, `npx`, `yarn`, `pnpm`, and `uv`.

---

## Shell Command Security (`utils.py`)

The `DANGEROUS_SHELL_PATTERNS` constant is a tuple of shell metacharacters that indicate unsafe command composition:

```python
DANGEROUS_SHELL_PATTERNS = (
    "$(",       # Command substitution
    "`",        # Backtick command substitution
    "\n",       # Newline (command injection)
    "${",       # Variable expansion
    "<<",       # Here-document
    ">>",       # Append redirect
    ">",        # Output redirect
    "<(",       # Process substitution
    # ... and more
)
```

The `contains_dangerous_patterns()` function checks commands against this list and also detects bare variable expansion (`$HOME`) and standalone `&` (background execution).

### Content Block Conversion

`utils.py` provides converters between Deep Agent internal content representations and ACP content blocks. Audio conversion deliberately raises `NotImplementedError` since ACP editors do not currently support audio playback. For how the content block format relates to the agent's message reducer, see [09_messages_reducer.md](./09_messages_reducer.md).

---

## Deployment Patterns

### Embedded in an Editor

The primary deployment model is embedding inside an ACP-compatible editor. The editor launches the ACP server as a subprocess:

```
Editor (Zed)
  +-- ACP transport (stdio / local socket)
       +-- AgentServerACP
            +-- create_deep_agent() graph
                 +-- LLM provider (Anthropic, OpenAI, etc.)
                 +-- CompositeBackend (filesystem + shell)
```

### Standalone Testing

```bash
python -m deepagents_acp
```

This calls `_serve_test_agent()`, which wires up a `CompositeBackend` with a `LocalShellBackend` and starts the ACP runtime. See [10_backends.md](./10_backends.md) for the backend composition model.

---

## Concurrency and Cancellation

- **Session serialization.** Within a single session, requests are serialized through the LangGraph checkpoint. Two concurrent `prompt()` calls to the same session would corrupt state.
- **Cross-session parallelism.** Different sessions run independently and can execute in parallel.
- **Cancellation.** The `cancel()` method cancels the in-flight LangGraph invocation for a given session, terminating tool execution and streaming.

---

## Relationship to Other Packages

The ACP server is one of three deployment surfaces for Deep Agents:

| Surface            | Package            | Description                                           |
|--------------------|--------------------|-------------------------------------------------------|
| Editor integration | `deepagents-acp`   | This package. ACP protocol translation layer.         |
| Terminal TUI       | `deepagents-code`  | Interactive terminal agent. See [25_code_agent.md](./25_code_agent.md). |
| Multi-channel host | `deepagents-talon` | WhatsApp/cron runtime. See [26_talon.md](./26_talon.md).               |
| Deployment CLI     | `deepagents-cli`   | Agent bundling and deploy. See [24_cli_deploy.md](./24_cli_deploy.md). |

All three deployment surfaces share the same underlying `create_deep_agent()` graph builder and SDK middleware stack (see [11_middleware.md](./11_middleware.md)).
