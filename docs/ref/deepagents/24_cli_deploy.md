# Document 24 -- CLI and Deployment Pipeline

## Purpose

The `deepagents-cli` package provides the command-line interface for initializing, configuring, and deploying **Managed Deep Agents** to the LangGraph Platform. It lives in `libs/cli/` and is installed as the `deepagents` and `deepagents-cli` console scripts. The package handles project scaffolding, payload building, MCP-server resolution, and deployment state tracking.

| Attribute       | Value                                       |
|-----------------|---------------------------------------------|
| Package name    | `deepagents-cli`                            |
| Version         | 0.2.2                                       |
| Python          | >= 3.11                                     |
| Entry points    | `deepagents` and `deepagents-cli` (both map to `deepagents_cli:cli_main`) |
| Source location | `libs/cli/`                                 |

> **Note:** The `deepagents` command used to launch the interactive REPL. Since v0.1.0, that functionality moved to `deepagents-code` (see [25_code_agent.md](./25_code_agent.md)). Bare invocations now print a deprecation notice and exit with code 1.

---

## Package Layout

```
libs/cli/deepagents_cli/
    __init__.py           # exposes cli_main (the console-script entry)
    __main__.py           # `python -m deepagents_cli`
    main.py               # CLI entry point, subcommand dispatch
    config.py             # dotenv / settings helpers
    model_config.py       # DEEPAGENTS_CLI_ env-var resolution
    _version.py           # Package version
    py.typed
    deploy/
        __init__.py
        commands.py        # init, deploy, agents, mcp-servers subcommands
        payload.py         # Build deployment payloads
        project.py         # Project file discovery and validation
        api_client.py      # HTTP client for the LangGraph Platform API (was api.py)
        mcp_resolver.py    # Resolve MCP-server configuration for the bundle
        state.py           # Local deployment-state tracking
```

> The earlier `auth.py` (OAuth device flow) and `directories.py` (directory
> syncing) modules no longer exist, and `api.py` was renamed `api_client.py`.

---

## Subcommands

### `deepagents init`

Scaffolds a new Managed Deep Agents project. Creates the standard project layout:

```
my-agent/
    agent.json           # Agent configuration (name, model, provider)
    AGENTS.md            # System prompt and behavioral instructions
    tools.json           # Tool declarations
    skills/              # Skill definitions (SKILL.md files)
    subagents/           # Subagent definitions
```

The init command prompts for agent name, model provider, and model name. It writes `agent.json` with the selected configuration and creates a default `AGENTS.md` with placeholder instructions. For how subagent definitions work, see [17_subagents.md](./17_subagents.md).

### `deepagents deploy`

Deploys the project to the LangGraph Platform. The deployment pipeline has four stages:

1. **Authentication** -- Resolves API credentials via OAuth device flow or cached tokens.
2. **Project validation** -- Reads `agent.json`, validates required fields, discovers project files.
3. **Payload building** -- Packages project files into a deployment payload.
4. **API upload** -- Sends the payload to the platform API and monitors deployment status.

### `deepagents agents`

Lists deployed agents and their status. Supports `--json` output for scripting.

### `deepagents mcp-servers`

Manages MCP server configurations for deployed agents. Supports add, remove, and list operations.

---

## Project Structure (`project.py`)

The `project.py` module handles project file discovery and validation. It defines the canonical project layout and knows how to find, read, and validate each file type.

### `agent.json` Schema

```json
{
  "name": "my-agent",
  "model": "claude-sonnet-4-20250514",
  "model_provider": "anthropic",
  "tools": ["read_file", "edit_file", "execute"],
  "interrupt_on": {
    "execute": true,
    "write_file": true
  }
}
```

Key fields:

| Field            | Required | Description                                              |
|------------------|----------|----------------------------------------------------------|
| `name`           | Yes      | Agent display name                                       |
| `model`          | Yes      | Model identifier                                         |
| `model_provider` | Yes      | Provider name (anthropic, openai, google, etc.)          |
| `tools`          | No       | List of enabled tool names                               |
| `interrupt_on`   | No       | Map of tool names to HITL approval requirements          |

### AGENTS.md

The system prompt file. Its contents are injected as the agent's system message at runtime. This is the same format used by the core SDK's graph builder (see [06_graph.md](./06_graph.md)).

### tools.json

Declares custom tool schemas beyond the built-in set. Each entry specifies a tool name, description, and JSON Schema for the input parameters.

---

## Payload Building (`payload.py`)

The `build_payload()` function packages the project into a deployment-ready archive:

```python
def build_payload(
    project_dir: Path,
    *,
    agent_config: AgentConfig,
    files: dict[str, bytes],
) -> DeployPayload:
```

The payload includes:
- `agent.json` -- agent configuration
- `AGENTS.md` -- system prompt
- `tools.json` -- custom tool definitions
- `skills/` -- all skill directories with their `SKILL.md` files
- `subagents/` -- subagent definition files
- `.mcp.json` -- MCP server configurations (if present)

Files are read from disk, validated, and packed into a `DeployPayload` dataclass. Binary files and files matching ignore patterns (`.git/`, `__pycache__/`, `node_modules/`) are excluded.

---

## Authentication (`auth.py`)

The CLI uses **OAuth device flow** for authentication:

1. The CLI requests a device code from the auth server.
2. The user is shown a URL and a code to enter in their browser.
3. The CLI polls the auth server until the user completes authorization.
4. The access token is cached locally for subsequent commands.

Token caching uses the platform's standard credential storage (`~/.deepagents/auth.json`). Tokens are refreshed automatically when expired.

---

## Directory Syncing (`directories.py`)

The `sync_directories()` function manages incremental updates to deployed agent resources:

- **Skills** -- Compares local `skills/` contents with the deployed version and uploads only changed or new skill definitions.
- **Subagents** -- Same incremental sync for `subagents/` definitions.
- **MCP configs** -- Syncs `.mcp.json` and related MCP server configurations.

This avoids re-uploading the entire project for small changes. The sync uses content hashing to detect modifications.

---

## API Client (`api.py`)

The API client communicates with the LangGraph Platform:

```python
class DeployAPIClient:
    def __init__(self, base_url: str, token: str) -> None:
        ...

    async def deploy(self, payload: DeployPayload) -> DeployResult: ...
    async def list_agents(self) -> list[AgentInfo]: ...
    async def get_agent(self, agent_id: str) -> AgentInfo: ...
    async def delete_agent(self, agent_id: str) -> None: ...
```

The client handles:
- **Retry logic** with exponential backoff for transient failures.
- **Deployment status polling** -- after upload, the client polls until the deployment reaches a terminal state (success or failure).
- **Error classification** -- distinguishes auth errors, validation errors, and server errors for clear user-facing messages.

---

## Environment and Configuration

### Dotenv Loading

The CLI loads environment variables from `.env` files with a three-tier precedence:

1. **Process environment** -- already-set variables take priority.
2. **Project `.env`** -- in the project root directory.
3. **Global `.env`** -- in `~/.deepagents/.env`.

This matches the same dotenv precedence used by `deepagents-code` (see [25_code_agent.md](./25_code_agent.md)).

### Environment Variables

| Variable                     | Purpose                                  |
|------------------------------|------------------------------------------|
| `DEEPAGENTS_API_URL`         | Override the platform API base URL       |
| `DEEPAGENTS_API_KEY`         | API key (alternative to OAuth)           |
| `DEEPAGENTS_AUTH_TOKEN`      | Pre-set OAuth token                      |
| `ANTHROPIC_API_KEY`          | Anthropic provider key                   |
| `OPENAI_API_KEY`             | OpenAI provider key                      |

---

## Deployment Lifecycle

The full deployment flow from `deepagents init` to a running agent:

```
deepagents init
  +-- Scaffold project (agent.json, AGENTS.md, tools.json, skills/, subagents/)

deepagents deploy
  +-- Authenticate (OAuth device flow or cached token)
  +-- Validate project structure
  +-- Build deployment payload
  +-- Upload to LangGraph Platform
  +-- Poll until deployment completes
  +-- Report deployment URL

Platform runs the agent:
  +-- Loads agent.json + AGENTS.md
  +-- Builds graph via create_deep_agent()
  +-- Serves via ACP (see 23_acp_server.md)
```

Once deployed, the agent is accessible through ACP-compatible editors (see [23_acp_server.md](./23_acp_server.md)) or through the platform's API. The deployed agent uses the same `create_deep_agent()` graph builder as all other deployment surfaces.

---

## Relationship to Other Packages

| Package            | Relationship                                                               |
|--------------------|----------------------------------------------------------------------------|
| `deepagents`       | Core SDK. Deployed agents use `create_deep_agent`. See [06_graph.md](./06_graph.md). |
| `deepagents-code`  | Terminal agent. Shares dotenv loading and project format. See [25_code_agent.md](./25_code_agent.md). |
| `deepagents-acp`   | Deployed agents are served via ACP. See [23_acp_server.md](./23_acp_server.md). |
| `deepagents-talon` | Fleet exports consume the same project format. See [26_talon.md](./26_talon.md). |

The CLI is the bridge between local development and cloud deployment. It takes the same project structure used for local `deepagents-code` sessions and packages it for the managed platform.
