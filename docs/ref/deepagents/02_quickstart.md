# Quickstart

This guide walks you through installing Deep Agents, running your first agent, and exploring the key configuration options that let you customize behavior for your use case.

## Prerequisites

- **Python >= 3.11** is required. Deep Agents relies on language features and standard library modules introduced in Python 3.11; earlier versions are not supported.
- **uv** -- Deep Agents uses [uv](https://docs.astral.sh/uv/) as its package manager. If you do not already have uv installed, follow the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

## Installation

Install the core framework into your project:

```bash
uv add deepagents
```

This pulls in the Deep Agents library and all required dependencies. Do not use `pip install` or `poetry add` -- the project is built around uv and its lockfile.

If you also want the terminal interface (Deep Agents Code), install it alongside the core library:

```bash
uv add deepagents-code
```

Alternatively, you can install Deep Agents Code via the standalone installer script:

```bash
curl -LsSf https://langch.in/dcode | bash
```

## Environment Setup

Before running an agent, you need to set at least one model-provider API key as an environment variable. The key name depends on which provider you use:

| Provider | Environment Variable | How to obtain |
|----------|---------------------|---------------|
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Anthropic | `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| Google | `GOOGLE_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

Set the key in your shell before running your script:

```bash
export OPENAI_API_KEY="sk-..."
```

Or place it in a `.env` file at your project root (loaded automatically via `python-dotenv`):

```dotenv
OPENAI_API_KEY=sk-...
```

If you forget to set a key, the agent will raise a clear error at model-construction time indicating which variable is missing.

## Your First Agent

The simplest way to get started is the `create_deep_agent` factory function. It returns a fully configured agent that can plan, execute tools, read and write files, and manage its own context window -- all out of the box.

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="openai:gpt-5.5",
    system_prompt="You are a research assistant.",
)

result = agent.invoke({"messages": "Research LangGraph and write a summary"})
```

What happens when you call `invoke`:

1. The agent receives your input message.
2. The underlying LLM generates a response. If the response includes tool calls (for example, searching the web or writing a file), the agent executes those tools automatically.
3. Tool results are fed back to the LLM, which can issue further tool calls or produce a final answer.
4. This loop repeats until the LLM determines the task is complete and returns a final response.

The returned `result` contains the full conversation state, including all intermediate messages and tool outputs.

## Model Providers

Deep Agents works with any LLM that supports tool calling. You specify the model using a string in the format `provider:model-name`. The provider prefix tells Deep Agents which API client to use, and the model name is passed through to that provider.

Supported provider strings include:

| Provider string    | Example model identifier               |
| ------------------ | -------------------------------------- |
| `openai`           | `openai:gpt-5.5`                      |
| `anthropic`        | `anthropic:claude-sonnet-4-6`         |
| `google-genai`     | `google-genai:gemini-2.5-pro`          |

Any provider that exposes a tool-calling-compatible API can be plugged in following this same pattern. The model string is the single point of configuration for switching between providers -- no other code changes are necessary.

```python
# Switch to Anthropic
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    system_prompt="You are an expert code reviewer.",
)

# Switch to Google
agent = create_deep_agent(
    model="google-genai:gemini-2.5-pro",
    system_prompt="You are a data analyst.",
)
```

## Adding Custom Tools

Deep Agents tools are standard LangChain `StructuredTool` instances. You can define your own tools and pass them to the agent at creation time.

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class SearchInput(BaseModel):
    query: str = Field(description="The search query to execute")


def search_database(query: str) -> str:
    """Search the internal knowledge base and return matching results."""
    # Your implementation here
    return f"Results for: {query}"


search_tool = StructuredTool.from_function(
    func=search_database,
    name="search_database",
    description="Search the internal knowledge base for relevant information.",
    args_schema=SearchInput,
)

agent = create_deep_agent(
    model="openai:gpt-5.5",
    tools=[search_tool],
    system_prompt="You are a helpful assistant with access to our knowledge base.",
)
```

The agent automatically discovers the tool's name, description, and parameter schema. The LLM will decide when to call the tool based on the user's request and the tool's description.

## Customizing the System Prompt

The `system_prompt` parameter defines the persona and behavioral instructions for the agent. A well-written system prompt significantly improves the quality and relevance of the agent's responses.

```python
agent = create_deep_agent(
    model="openai:gpt-5.5",
    system_prompt="""You are a senior software architect.

When analyzing code:
- Identify architectural patterns and anti-patterns.
- Suggest concrete improvements with code examples.
- Consider maintainability, testability, and performance.
- Always explain the reasoning behind your recommendations.
""",
)
```

## Streaming vs. Invoke

Deep Agents supports two execution modes: **invoke** and **streaming**.

### Invoke

`invoke` runs the full agent loop to completion and returns the final state. This is the simplest interface and is appropriate when you want the final result without observing intermediate steps.

```python
result = agent.invoke({"messages": "Summarize this document."})
```

### Streaming

Streaming lets you observe the agent's work as it happens. Each event is yielded as it occurs -- you see LLM tokens, tool calls, and tool results in real time.

```python
for event in agent.stream({"messages": "Analyze the project structure."}):
    # Each event contains the incremental state update
    print(event)
```

Streaming is particularly useful for:

- Building interactive UIs that show progress.
- Debugging agent behavior by observing the sequence of tool calls.
- Long-running tasks where you want to confirm the agent is on track.

## Configuring Sub-agents

For complex tasks, you can configure the agent to delegate work to isolated sub-agents. Each sub-agent runs in its own context window, receives a focused instruction from the parent, executes independently, and returns a summary result. This keeps large tasks from exhausting the parent's context.

Sub-agents are configured with the first-class `subagents=` parameter of `create_deep_agent` (a list of `SubAgent` / `CompiledSubAgent` / `AsyncSubAgent` specs); they can also be shaped by agent profiles. The `SubAgentMiddleware` injects a `task` tool that the LLM calls to delegate to a named sub-agent on demand. See [17_subagents.md](./17_subagents.md) for the full sub-agent lifecycle and [20_profiles.md](./20_profiles.md) for how profiles enable or constrain sub-agents.

## Using Deep Agents Code (Terminal Interface)

Deep Agents Code is an interactive terminal interface for working with Deep Agents. It provides a conversational coding experience directly in your terminal, with access to your filesystem, shell, and all configured tools.

### Installation

Install via the standalone script:

```bash
curl -LsSf https://langch.in/dcode | bash
```

Or add it to your project:

```bash
uv add deepagents-code
```

### Entry Points

After installation, two commands are available:

- **`deepagents-code`** -- the full command name.
- **`dcode`** -- a shorter alias for convenience.

Both commands launch the same interactive terminal session.

```bash
# Either of these starts the terminal interface
deepagents-code
dcode
```

Once inside the terminal interface, you can issue natural-language instructions. The agent will read and write files in your project, execute shell commands, and manage its own context as needed.

## What the Agent Can Do Out of the Box

Without any custom configuration, a Deep Agents instance can:

- **Plan**: Break down complex tasks into steps and execute them sequentially.
- **Read and write files**: Access the local filesystem to read source code, write output files, and modify existing files.
- **Execute shell commands**: Run arbitrary shell commands and process their output.
- **Manage its own context**: Automatically summarize long conversations, evict old messages, and clip overflows to stay within the model's context window.
- **Use tools**: Call any tools you provide, plus built-in tools for file operations and search.

## Next Steps

- Read the [Concepts](03_concepts.md) guide for a detailed explanation of the architecture -- agent graphs, state, backends, middleware, and more.
- Explore the source code to see how profiles, middleware, and backends are composed.
- Try building a custom tool and integrating it into an agent for your specific workflow.
