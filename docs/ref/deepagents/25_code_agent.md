# Document 25 — Deep Agents Code (`dcode`)

> **This document was rewritten to match the current codebase (~300 commits
> ahead of the previous version).** It is now a concise, accurate overview and
> the entry point for the **dedicated `dcode` architecture set** in
> [`docs/dcode/`](dcode/README.md), which covers everything in depth with
> sequence/architecture diagrams and exact source references.

Deep Agents Code (`deepagents-code`, commands `dcode` / `deepagents-code`) is the
interactive terminal coding agent shipped as a pre-built consumer of the Deep
Agents SDK. It is a **client/server application**: a Textual TUI connects over
HTTP to a private `langgraph dev` subprocess that hosts an SDK agent graph built
by `create_deep_agent()`.

| Attribute | Value |
|-----------|-------|
| Package | `deepagents-code` |
| Source | [`libs/code/`](../libs/code) |
| Console scripts | `deepagents-code`, `dcode` |
| UI framework | Textual |
| Python | ≥ 3.11 |
| SDK seam | `create_deep_agent()` — [`agent.py:3026`](../libs/code/deepagents_code/agent.py) |

---

## What belongs to the SDK vs. what `dcode` adds

- **SDK owns:** `create_deep_agent`, the middleware protocol, backends
  (`FilesystemBackend`, `LocalShellBackend`, `CompositeBackend`,
  `SandboxBackendProtocol`), the subagent runner, and base middleware
  (`Filesystem`, `Memory`, `Skills`, `Summarization`, `Rubric`).
- **`dcode` adds:** the CLI, TUI, client/server launcher, a **17-layer middleware
  stack**, approvals/auto-mode, hooks, plugins, goal/rubric self-evaluation,
  context offload/compaction, MCP integration, sandbox provider registry, session
  persistence, and configuration/model resolution.

The single integration point is `create_cli_agent()` → `create_deep_agent()`.
See [dcode/02_agent_construction.md](dcode/02_agent_construction.md).

---

## Execution flow (summary)

```
dcode → cli_main() [main.py] → run_textual_cli_async() → run_textual_app() [app.py]
     → start_server_and_get_agent() [client/launch/server_manager.py]
       → ServerProcess: `langgraph dev` subprocess (client/launch/server.py)
         → server_graph.make_graph() → create_cli_agent() → create_deep_agent()
     → RemoteAgent.astream() (SSE) → TextualUIAdapter renders + brokers interrupts
```

Full trace with sequence diagrams: [dcode/01_execution_flow.md](dcode/01_execution_flow.md).

---

## The middleware stack (append order in `create_cli_agent`)

1. `ConfigurableModelMiddleware` · 2. `_GlmTerminalStallRecovery` (headless) ·
3. `HeadlessMCPGuardMiddleware` (headless+gated MCP) · 4. `ResumeStateMiddleware` ·
5. `GoalToolsMiddleware` · 6. `AskUserMiddleware` · 7. `MemoryMiddleware` +
`ManagedMemoryGuardMiddleware` · 8. `PluginSkillsMiddleware` ·
9. `CodeInterpreterMiddleware` (interpreter) · 10. `LocalContextMiddleware` ·
11. `ShellAllowListMiddleware` · 12. `AutoModeHITLMiddleware` **or**
`AsyncApprovalHITLMiddleware` · 13. `ServerHooksMiddleware` · 14. `FilesystemMiddleware`
(`--allow-fs-tools`) · 15. `GoalCriteriaMiddleware` · 16. `CLICompactionMiddleware` ·
17. `ReliableRubricMiddleware`.

`create_deep_agent` is then called with `interrupt_on={}` (dcode owns HITL),
`context_schema=CLIContextSchema`, the composite backend, subagents, and a
checkpointer. Detail + rationale: [dcode/02_agent_construction.md](dcode/02_agent_construction.md).

---

## Major components (and where they're documented)

| Component | Key files | Doc |
|-----------|-----------|-----|
| CLI / dispatch | `main.py`, `client/commands/` | [01](dcode/01_execution_flow.md) |
| Client/server launch | `client/launch/server.py`, `server_manager.py`, `server_graph.py` | [01](dcode/01_execution_flow.md) |
| Agent construction | `agent.py` (`create_cli_agent`) | [02](dcode/02_agent_construction.md) |
| Tools (`web_search`, `fetch_url`, …) | `tools.py` | [03](dcode/03_subsystems.md) |
| Memory + guard | SDK `MemoryMiddleware`, `memory_guard.py`, `onboarding.py` | [03](dcode/03_subsystems.md) |
| Skills | `skills/`, `built_in_skills/`, `PluginSkillsMiddleware` | [03](dcode/03_subsystems.md) |
| Context offload / compaction | `offload.py`, `offload_middleware.py` | [03](dcode/03_subsystems.md) |
| MCP | `mcp_tools.py`, `mcp_config.py`, `mcp_auth.py`, `mcp_providers/` | [03](dcode/03_subsystems.md) |
| Sandbox | `integrations/`, SDK `SandboxBackendProtocol`, partners | [03](dcode/03_subsystems.md) |
| Sessions / resume | `sessions.py`, `resume_state.py`, `state_migration.py` | [03](dcode/03_subsystems.md) |
| Config / model | `config.py`, `model_config.py`, `configurable_model.py` | [03](dcode/03_subsystems.md) |
| Hooks (v2 + legacy) | `hooks/` | [04](dcode/04_hooks_and_plugins.md) |
| Plugins | `plugins/` | [04](dcode/04_hooks_and_plugins.md) |
| Approvals / Auto mode | `approval_mode.py`, `auto_mode.py` | [05](dcode/05_approvals_goals_rubric.md) |
| Goal / rubric | `goal_tools.py`, `goal_rubric.py`, `reliable_rubric.py` | [05](dcode/05_approvals_goals_rubric.md) |
| TUI / client | `app.py`, `tui/`, `client/remote_client.py`, `event_bus.py` | [06](dcode/06_tui_and_client.md) |
| Extensibility / design | (cross-cutting) | [07](dcode/07_extensibility_and_design.md) |

---

## Storage locations (current)

- Config: `~/.deepagents/config.toml`, `~/.deepagents/.env`
- State dir: `~/.deepagents/.state/`
  - **Sessions DB: `~/.deepagents/.state/sessions.db`** (SQLite via
    `AsyncSqliteSaver`; UUID7 thread IDs)
  - MCP tokens: `~/.deepagents/.state/mcp-tokens/`
  - Approvals: `~/.deepagents/.state/approval.json`
- Plugins cache: `~/.deepagents/plugins/`
- Hooks: `~/.deepagents/hooks.json` + project `.deepagents/hooks.json`
- Memory: `~/.deepagents/{agent}/AGENTS.md` + project `AGENTS.md`

---

## Key changes since the previous version of this document

- **Package reorg:** `server.py` → `client/launch/`; `widgets/`/`textual_adapter.py`
  → `tui/`; `*_commands.py` → `client/commands/`; `hooks.py` → `hooks/` package.
- **New subsystems:** plugins, Hooks v2 (server-owned lifecycle events over the
  interrupt channel), goal/rubric self-evaluation, classifier-backed Auto mode,
  context offload/compaction, `doctor`/`tools` diagnostics.
- **Removed:** `FilesystemEmptyResultMiddleware`.
- **Approval model:** boolean `auto_approve` → three-way `ApprovalMode`
  (manual/auto/yolo), per-thread persisted.
- **Session DB** is `sessions.db` (the previous doc said `threads.db`).
- **Skills precedence** now inserts **plugin** sources between built-in and user
  skills, with `{plugin_id}:{skill_name}` namespacing.

For everything in depth, start at [dcode/README.md](dcode/README.md).
