# 26 -- Talon: Multi-Channel Agent Runtime

> **Source package**: `libs/talon/deepagents_talon/`
> **Stability**: Experimental -- subject to change or removal at any time.

## Purpose

Talon is an asynchronous runtime that bridges a Deep Agent with external communication channels (currently **WhatsApp** and **Telegram**) and a cron scheduler. It runs as a long-lived process, accepting inbound messages from channels, routing them through the agent, and delivering responses back. Talon reuses the same `create_deep_agent()` graph builder used by `deepagents-code` (see [25_code_agent.md](./25_code_agent.md)) and `deepagents-acp` (see [23_acp_server.md](./23_acp_server.md)), adding multi-channel routing, tool approval over chat, scheduled execution, async (remote) subagents (`async_subagents.py`), and zip-based fleet import on top.

> **Changed since the previous docs:** a **Telegram** channel (`channels/telegram.py`,
> `TelegramChannel`/`TelegramChannelConfig`) was added alongside WhatsApp; the old
> `fleet.py` was replaced by `fleet_import.py` (see the Fleet section); the concrete
> agent runtimes are now `DeepAgentRuntime` / `EchoAgentRuntime` (`runtime.py`).

---

## TalonHost -- Central Orchestrator (`host.py`)

`TalonHost` is the top-level async coordinator. It manages channels, the scheduler, the agent runtime, and media delivery within a single event loop.

### Constructor

```python
class TalonHost:
    def __init__(
        self,
        *,
        config: TalonConfig,
        agent: AgentRuntime,
        channels: Sequence[ChannelAdapter] = (),
        scheduler: CronScheduler | None = None,
        voice_transcriber: VoiceTranscriber | None = None,
    ) -> None:
```

### Per-Conversation Locking

```python
self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
```

Each unique `conversation_id` gets its own `asyncio.Lock`. When the host receives an inbound message or a cron-triggered prompt, it acquires the conversation's lock before invoking the agent. This prevents two concurrent turns from racing on the same conversation state. The `defaultdict` factory means no explicit lock creation is needed.

### Signal Handling

The host installs handlers for `SIGINT` and `SIGTERM` during startup. When a signal arrives, it sets an internal shutdown event, then stops channels, the cron scheduler, and the agent runtime in sequence. The cleanup restores original signal handlers to avoid interference with outer frameworks.

### Tool Approval Flow

When the agent requests human-in-the-loop approval for a tool call, Talon routes the approval request through the originating channel:

```python
_APPROVE_REPLIES = frozenset({"approve", "approved", "yes", "y"})
_DENY_REPLIES = frozenset({"deny", "denied", "reject", "rejected", "no", "n"})
```

The flow:
1. The agent runtime encounters a LangGraph interrupt requesting tool approval.
2. The host creates a `_PendingToolApproval` with an `asyncio.Future` and sends the request to the user via the channel adapter.
3. The user's reply is matched against approve/deny keyword sets.
4. The future is resolved, unblocking the agent runtime.

Sender validation ensures only the user who triggered the original turn can approve or deny -- a different user in the same conversation cannot hijack the approval. Compare this with the ACP server's HITL flow in [23_acp_server.md](./23_acp_server.md).

---

## Agent Runtime (`runtime.py`)

The runtime module creates and configures the Deep Agent graph for Talon's needs:

```python
DEFAULT_RECURSION_LIMIT = 150
DEFAULT_MAX_RETRIES = 3
```

It uses `create_deep_agent` with `LocalShellBackend` and `InMemorySaver` as the checkpoint saver. The middleware stack includes `SummarizationToolMiddleware` (for context window management -- see [13_summarization_middleware.md](./13_summarization_middleware.md)) and `CronTools` (which give the agent the ability to create and manage scheduled jobs).

### Environment Security

The runtime enforces strict environment variable controls:

- **`_BACKEND_ENV_ALLOWED_KEYS`** -- whitelist of environment variables that may be passed to shell backend subprocesses.
- **`_BACKEND_ENV_HIJACK_KEYS`** -- variables that are forcibly overridden regardless of what the environment provides.

This prevents a misconfigured deployment from leaking secrets to agent-spawned processes. For the general backend security model, see [10_backends.md](./10_backends.md).

---

## Channel System

### Channel Exposure Policy (`channels/base.py`)

The `ExposureMode` enum controls who may trigger an agent through a channel:

```python
class ExposureMode(StrEnum):
    SELF = "self"          # Only the operator's own messages
    ALLOWLIST = "allowlist" # Specific conversation IDs
    OPEN = "open"          # Any sender
```

The `ChannelExposure` dataclass combines mode, operator ID, conversation allowlist, and mention patterns into a single policy:

```python
@dataclass(frozen=True, slots=True)
class ChannelExposure:
    mode: ExposureMode = ExposureMode.SELF
    operator_id: str | None = None
    conversations: frozenset[str] = field(default_factory=frozenset)
    mention_patterns: tuple[str, ...] = ()

    def allows(self, message: ChannelMessage) -> bool:
        if self.mode == ExposureMode.OPEN:
            return True
        if self.mode == ExposureMode.SELF:
            return _is_self_message(message, self.operator_id)
        return message.conversation_id in self.conversations or \
               _matches_text(message.text, self.mention_patterns)
```

### Message Formatting

`format_markdown_for_channel()` converts common Markdown into WhatsApp-compatible text by stripping headings, converting links to inline format, and mapping bold/italic syntax. `chunk_text()` splits long responses into channel-sized chunks (default `MAX_TEXT_CHARS = 4096`).

### WhatsApp Channel (`channels/whatsapp.py`)

The WhatsApp adapter uses a Node.js bridge subprocess for the WhatsApp Web protocol:

```python
@dataclass(frozen=True, slots=True)
class WhatsAppChannelConfig:
    session_dir: Path       # WhatsApp session persistence
    bridge_settings: dict   # Node bridge configuration
```

`WhatsAppChannelConfig.from_talon_config()` extracts configuration from the global `TalonConfig`. The bridge is spawned as a child process, and communication happens over stdio. `WhatsAppBridgeError` is raised for protocol-level failures.

---

## Cron Scheduling

### Job Model (`cron/jobs.py`)

Cron jobs are persistent records with minute-granularity scheduling:

```python
MIN_GRANULARITY_MINUTES = 1

JobStatus = Literal["ok", "error"]
ScheduleKind = Literal["one_shot", "recurring"]
```

The `CronJob` dataclass captures schedule (interval in minutes), repeat cap (optional max execution count), origin (the `conversation_id`, `channel`, and `message_id` that created the job), and status tracking (`last_run_at`, `last_status`, `last_error`, `next_run_at`).

### Scheduler (`cron/scheduler.py`)

```python
class PersistentCronScheduler:
    def __init__(
        self,
        *,
        store: CronJobStore,
        run_job: RunCronJob,
        deliver_result: DeliverCronResult,
        tick_seconds: float = DEFAULT_TICK_SECONDS,  # 60.0
        now: NowFactory | None = None,
    ) -> None:
```

The scheduler runs a ticker loop that scans for due jobs every `tick_seconds`. For each due job:

1. **Claim** -- `store.advance_next_run()` atomically claims the job and computes the next run time.
2. **Execute** -- `run_job(claimed)` invokes the agent with the job's prompt.
3. **Deliver** -- If the result is not silent (does not start with `SILENT_SENTINEL = "[SILENT]"`), it is delivered back to the originating conversation.
4. **Record** -- `store.mark_job_run()` records success or failure.

The `now` parameter enables deterministic testing by injecting a clock override.

---

## Fleet Import (`fleet_import.py`)

> **Changed since the previous docs:** the old `fleet.py` (with
> `load_fleet_agent_components()` and a `FleetAgentComponents` dataclass) was
> replaced by `fleet_import.py`, which implements a **zip-based import** model.

Talon can import an agent bundle from a **Fleet export zip** produced by the
managed Deep Agents platform. The public surface (`fleet_import.py`, imported by
`__main__.py`) is:

- `import_fleet_zip(...)` -- extracts and validates a Fleet export zip into the
  local Talon working layout.
- `format_import_stdout(...)` -- renders a human-readable summary of what was
  imported.
- `FleetImportResult` -- the structured result of an import.
- `FleetImportError` -- raised on a malformed or invalid bundle.

Fleet exports follow the same `agent.json` + `AGENTS.md` + tools/skills layout
used by `deepagents-cli` deploys (see [24_cli_deploy.md](./24_cli_deploy.md)).

---

## Observability

Talon uses structured logging via `log_event()` for all lifecycle events:

```python
log_event(logger, "cron.tick", due_count=len(jobs), now=current.isoformat())
log_event(logger, "cron.dispatch", job_id=claimed.id, job_name=claimed.name)
log_event(logger, "fleet.mcp_surface", server_count=len(records))
```

LangSmith tracing is integrated via `langsmith_trace_context()`. For the broader observability model, see [20_profiles.md](./20_profiles.md).

---

## Relationship to Other Packages

| Package            | Relationship                                                               |
|--------------------|----------------------------------------------------------------------------|
| `deepagents`       | Core SDK providing `create_deep_agent`. See [06_graph.md](./06_graph.md). |
| `deepagents-code`  | Terminal agent -- same graph, different surface. See [25_code_agent.md](./25_code_agent.md). |
| `deepagents-acp`   | Editor integration -- same graph, ACP transport. See [23_acp_server.md](./23_acp_server.md). |
| `deepagents-cli`   | Deploys the project format that Fleet exports consume. See [24_cli_deploy.md](./24_cli_deploy.md). |
| `deepagents-evals` | Evaluation framework with sandboxed execution. See [27_evals.md](./27_evals.md). |

Talon is the only deployment surface that adds channel routing and scheduled execution. The code agent and ACP server handle interactive single-user sessions; Talon handles multi-user, asynchronous, and scheduled workloads.
