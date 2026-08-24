# Document 11 -- Middleware System Overview

## What Is Middleware?

Middleware in Deep Agents is the primary mechanism for extending and modifying agent behavior without touching the core agent loop. Each middleware is a Python class that intercepts and transforms the data flowing between the agent, the language model, and the tools. Middleware can inject system prompt context, filter tools dynamically, transform messages, manage cross-turn state, and perform side effects -- all at well-defined interception points in the agent lifecycle.

The middleware system is what separates Deep Agents from a plain `create_agent` setup. The core agent loop (model proposes tool calls, framework executes them, results feed back) remains unchanged. Middleware wraps around that loop, adding capabilities like filesystem access, conversation summarization, sub-agent delegation, and persistent memory -- without modifying the loop itself.

---

## Why Middleware Instead of Plain Tools?

A natural question arises: why not just pass more tools to the agent? Tools give the model new actions, but they lack the ability to observe and modify every LLM request. Middleware can do things that tools fundamentally cannot:

| Capability | Tool | Middleware |
|---|---|---|
| Execute actions on behalf of the model | Yes | Yes |
| Inject dynamic system prompt content | No | Yes |
| Filter which tools the model sees per turn | No | Yes |
| Transform messages before they reach the model | No | Yes |
| Intercept and modify tool results after execution | No | Yes |
| Maintain private cross-turn state (invisible to the model) | No | Yes |
| React to context overflow errors and recover | No | Yes |
| Evict or compress messages to manage context limits | No | Yes |

Middleware operates at a level of abstraction above tools. A tool is something the model chooses to call. Middleware is something the framework applies unconditionally on every turn.

---

## The AgentMiddleware Base Class

All middleware in Deep Agents subclasses `AgentMiddleware`. This base class defines the hook methods that the agent loop calls at specific points during execution. The most important hook is `wrap_model_call()`, which intercepts every LLM request.

```python
from langchain.agents.middleware import AgentMiddleware

class MyMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        # Called before every LLM invocation.
        # request contains: messages, tools, system_message, state, runtime
        # handler is the next middleware (or the actual model call)
        modified_request = request.override(
            system_message=append_to_system_message(
                request.system_message,
                "Additional context for the model."
            )
        )
        return handler(modified_request)
```

The `request` object (`ModelRequest`) provides access to:

- **messages** -- The conversation history (list of AnyMessage).
- **tools** -- The tools currently available to the model.
- **system_message** -- The system message (can be augmented).
- **state** -- The current agent state dictionary.
- **runtime** -- The runtime context (access to config, store, stream writer).

The `handler` callable represents the next step in the middleware chain. If your middleware is the last one, `handler` calls the actual model. If there are more middleware layers, `handler` calls the next middleware's `wrap_model_call`. This chaining design means middleware composes naturally -- each layer wraps the next.

### Type Parameters

`AgentMiddleware` is a generic class with three type parameters:

```python
class AgentMiddleware(Generic[StateT, ContextT, ResponseT]):
    ...
```

- **StateT** (bound to `AgentState[Any]`) -- The agent state type. Middleware that needs custom state fields defines its own schema extending AgentState.
- **ContextT** (default None) -- The runtime context type, passed through via the Runtime object.
- **ResponseT** (default Any) -- The structured response type returned by model calls.

### Class Attributes

- **state_schema** -- Defines the state schema for the middleware. Defaults to a minimal AgentState. Middleware that introduces new state fields (like FilesystemState or SummarizationState) overrides this with its own schema class.
- **tools** -- Additional tools registered by the middleware. These are automatically merged into the agent's tool set during pipeline construction.
- **name** -- A property returning the class name of the middleware instance.

---

## Hook Methods

`AgentMiddleware` defines several categories of hooks. A middleware can override any combination of them.

### Lifecycle Hooks

These hooks fire at defined points in the agent's execution lifecycle:

| Hook | Async Variant | When It Fires |
|---|---|---|
| `before_agent(state, runtime)` | `abefore_agent(state, runtime)` | Once, before agent execution begins. Used for initialization. |
| `before_model(state, runtime)` | `abefore_model(state, runtime)` | Before each model call within the agent loop. |
| `after_model(state, runtime)` | `aafter_model(state, runtime)` | After each model call completes. |
| `after_agent(state, runtime)` | `aafter_agent(state, runtime)` | Once, after agent execution completes. Used for cleanup. |

Each lifecycle hook receives the current agent state and a runtime context, and returns either a dictionary of state updates to merge or None.

### Interception Hooks

These hooks wrap actual model and tool calls, enabling middleware to modify requests, responses, or both:

**wrap_model_call(request, handler) / awrap_model_call(request, handler)**

The primary hook. Called on every LLM invocation. Receives the ModelRequest and a handler to call the next layer. Can modify the request, inspect the response, or both.

```python
def wrap_model_call(self, request, handler):
    # Pre-model: modify request
    request = request.override(tools=filtered_tools)

    # Call the next layer (or the model itself)
    response = handler(request)

    # Post-model: inspect or modify response
    return response
```

**wrap_tool_call(request, handler) / awrap_tool_call(request, handler)**

Called around individual tool executions. Receives a ToolCallRequest and a handler. Useful for intercepting tool results (e.g., evicting oversized results to the filesystem).

```python
def wrap_tool_call(self, request, handler):
    result = handler(request)  # Execute the tool

    # Post-tool: inspect or modify the result
    if is_too_large(result):
        result = evict_to_filesystem(result)

    return result
```

### Return Types

`wrap_model_call` can return either a standard ModelResponse or an ExtendedModelResponse. The ExtendedModelResponse wraps a model response together with a Command that updates the agent state. This is how middleware communicates state changes (like tagging evicted messages) without mutating the state directly.

```python
from deepagents.middleware import ExtendedModelResponse

def wrap_model_call(self, request, handler):
    response = handler(request)
    if needs_state_update:
        return ExtendedModelResponse(
            model_response=response,
            command=Command(update={"messages": Overwrite(new_messages)})
        )
    return response
```

---

## Middleware Registration and Ordering

Middleware is registered when creating a Deep Agent. The `middleware` parameter accepts a list of AgentMiddleware instances, and they are applied in order -- the first middleware in the list is the outermost wrapper, and the last is closest to the model.

```python
from deepagents import create_deep_agent
from deepagents.middleware import (
    FilesystemMiddleware,
    SummarizationMiddleware,
    MemoryMiddleware,
)

agent = create_deep_agent(
    model="anthropic/claude-sonnet-4-20250514",
    middleware=[
        FilesystemMiddleware(backend=my_backend),
        SummarizationMiddleware(model="anthropic/claude-sonnet-4-20250514"),
        MemoryMiddleware(backend=my_backend),
    ],
)
```

The ordering matters because each middleware wraps the next. In the example above, FilesystemMiddleware gets the first chance to modify the request and the last chance to modify the response. The execution flow is:

```
Request arrives
  --> FilesystemMiddleware.wrap_model_call()
    --> SummarizationMiddleware.wrap_model_call()
      --> MemoryMiddleware.wrap_model_call()
        --> Actual model call
      <-- MemoryMiddleware returns
    <-- SummarizationMiddleware returns
  <-- FilesystemMiddleware returns
Response returned
```

For tool calls, the same nesting applies through wrap_tool_call.

---

## Middleware Lifecycle

Each turn of the agent loop involves a well-defined sequence of middleware interceptions. The full lifecycle for a single turn looks like this:

```
1. pre_model   -- wrap_model_call receives the request.
                  Middleware modifies system prompt, filters tools,
                  transforms messages, evicts oversized content.

2. model       -- The language model is invoked with the modified request.
                  (This is the handler() call at the innermost layer.)

3. post_model  -- wrap_model_call receives the response.
                  Middleware can inspect or transform the response,
                  attach state updates via ExtendedModelResponse.

4. pre_tool    -- If the model requested tool calls:
                  wrap_tool_call receives the tool request.

5. tool        -- The tool executes.
                  (This is the handler() call at the innermost layer.)

6. post_tool   -- wrap_tool_call receives the tool result.
                  Middleware can intercept oversized results,
                  evict content to filesystem, modify the result.
```

Steps 4-6 repeat for each tool call in the model's response. After all tool results are collected, the loop returns to step 1 for the next turn.

---

## State Management

Middleware can maintain private state across turns using typed state schemas and the `PrivateStateAttr` annotation. Private state fields are invisible to the model -- they exist in the agent state but are filtered out before messages are sent to the LLM.

```python
from typing import Annotated
from langchain.agents.middleware.types import PrivateStateAttr
from deepagents.state import AgentState

class SummarizationState(AgentState):
    _summarization_event: Annotated[
        SummarizationEvent | None,
        PrivateStateAttr,
    ] = None
```

The `private_state_field_names()` utility (in `_state.py`) scans state schemas for fields annotated with PrivateStateAttr and returns their names as a frozen set. The framework uses this to strip private fields before serializing state for the model.

The `_has_marker()` helper handles recursive Annotated type inspection, so private state works correctly even when combined with other annotations like DeltaChannel.

---

## SDK Middleware vs. Consumer-Provided Tools

Deep Agents distinguishes between two categories of tools:

1. **SDK middleware tools** -- Tools provided automatically by middleware (e.g., read_file, write_file, ls, grep from FilesystemMiddleware). These are registered as part of the middleware and injected into the tool list via wrap_model_call. The middleware has full control over their lifecycle.

2. **Consumer-provided tools** -- Tools passed directly via the `tools` parameter when creating the agent. These are user-defined and pass through middleware hooks like any other tool, but middleware does not own them.

This distinction matters for features like tool result eviction. The FilesystemMiddleware excludes its own tools (ls, glob, grep, read_file, edit_file, write_file) from large-result eviction because their results are already managed by the middleware itself. Only consumer-provided tools and the execute tool are subject to eviction via wrap_tool_call.

---

## Built-In Middleware

Deep Agents ships with the following middleware classes, all exported from `deepagents.middleware`:

| Middleware | Purpose | Key Capabilities |
|---|---|---|
| FilesystemMiddleware | File operations | ls, read_file, write_file, edit_file, glob, grep, delete, execute tools; permission checking; path sandboxing; large result eviction; video/multimodal file reading |
| SummarizationMiddleware | Context management | Automatic conversation summarization; backend offload of history; argument truncation; context overflow recovery; non-mutating state updates |
| SummarizationToolMiddleware | Manual summarization | Provides compact_conversation tool; eligibility gating at 50% of trigger threshold; system prompt nudges |
| PatchToolCallsMiddleware | Tool-call repair | Repairs dangling/invalid tool calls so the message history stays well-formed (part of the default stack) |
| MemoryMiddleware | Persistent memory | Cross-session memory storage and retrieval via the filesystem backend |
| SkillsMiddleware | Skill injection | Discovers and injects skill definitions into the system prompt |
| SubAgentMiddleware | Synchronous delegation | Delegates tasks to sub-agents and waits for results |
| AsyncSubAgentMiddleware | Asynchronous delegation | Launches sub-agents that run concurrently; provides status-checking tools |
| RubricMiddleware | Response evaluation | Applies rubric-based scoring to agent responses |

Each middleware is independent and composable. You can use any combination, and they stack cleanly via the middleware chain.

---

## Writing Custom Middleware

To create custom middleware, subclass AgentMiddleware and override the hooks you need. Here is a complete example of a middleware that adds a timestamp to every system prompt:

```python
from datetime import datetime, timezone
from langchain.agents.middleware import AgentMiddleware
from deepagents.middleware._utils import append_to_system_message


class TimestampMiddleware(AgentMiddleware):
    """Adds a UTC timestamp to every system prompt."""

    def wrap_model_call(self, request, handler):
        now = datetime.now(timezone.utc).isoformat()
        new_system = append_to_system_message(
            request.system_message,
            f"Current UTC time: {now}"
        )
        request = request.override(system_message=new_system)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        now = datetime.now(timezone.utc).isoformat()
        new_system = append_to_system_message(
            request.system_message,
            f"Current UTC time: {now}"
        )
        request = request.override(system_message=new_system)
        return await handler(request)
```

Key patterns to follow when writing custom middleware:

1. **Always call the handler.** The handler is the next layer in the chain. If you do not call it, the model never executes (or the tool never runs).

2. **Use request.override() to modify requests.** Do not mutate the request object directly. The override() method returns a new request with the specified fields replaced.

3. **Implement both sync and async variants.** The agent loop may run in either mode. If you only implement the sync version, the async code path will fail.

4. **Use append_to_system_message() for prompt injection.** This utility (from _utils.py) handles the case where the system message is None and avoids double-newline formatting issues.

5. **Return ExtendedModelResponse for state updates.** If your middleware needs to modify the agent state, wrap the model response in an ExtendedModelResponse with a Command.

6. **Declare private state fields with PrivateStateAttr.** If your middleware needs cross-turn state that should not be visible to the model, annotate the field in a state schema subclass.

---

## Utility Functions

The middleware system provides shared utility functions used across multiple middleware classes:

### append_to_system_message(system_message, text)

Located in `_utils.py`. Appends text to an existing SystemMessage, or creates a new one if the current system message is None. Returns a new SystemMessage instance.

### private_state_field_names(*state_schemas)

Located in `_state.py`. Scans one or more state schema classes and returns a frozenset of field names that are annotated with PrivateStateAttr. Used by the framework to filter private state before model invocations.

### _has_marker(annotation, marker)

Located in `_state.py`. Recursively inspects Annotated type hints to check whether a specific marker (like PrivateStateAttr) is present. Handles nested generics correctly.

---

## How Middleware Fits the Architecture

Middleware is the composition layer between the agent loop and the capabilities that make an agent useful. Without middleware, a Deep Agent is just a model calling tools in a loop. With middleware, it gains:

- **Filesystem awareness** -- The agent can read, write, and search files.
- **Context management** -- The agent automatically summarizes long conversations and evicts oversized content.
- **Delegation** -- The agent can spawn sub-agents for complex subtasks.
- **Memory** -- The agent remembers information across sessions.
- **Evaluation** -- The agent's responses can be scored against rubrics.

Each of these capabilities is implemented as a self-contained middleware class. They communicate through the agent state (using private fields where needed) and compose through the middleware chain. This design keeps the core agent loop simple and makes each capability independently testable, replaceable, and extensible.

The following documents in this series cover the major middleware classes in detail:

- **Document 12** covers FilesystemMiddleware -- file operations, permissions, backends, and result eviction.
- **Document 13** covers the context management middleware -- SummarizationMiddleware, message eviction, and overflow clipping.
