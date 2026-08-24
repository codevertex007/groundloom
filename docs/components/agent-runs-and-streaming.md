# Agent runs and streaming component

Owns agent threads, runs, durable public events, run steps/projections, todos, approvals, errors, cancellation, and user messages. Checkpoints remain runtime-owned but correlate by stable thread/run IDs.

Commands: create/send message, cancel, resume/approve, retry eligible failed scope. Queries: thread transcript view, run status, event replay, todos/steps. Persist public events with monotonically increasing per-run sequence through outbox; SSE may reconnect from last sequence.

Required tests: double submit, serialization policy, replay dedupe/order, API/worker restart, cancellation timing, approval expiry/resume, dangling tool call recovery, redaction, event schema compatibility, and no checkpoint leakage in DTOs.

Groundloom serializes one active mutation turn per project. A duplicate request
with the same idempotency key replays its existing run; a different request
while the project has a queued, running, or waiting run receives typed
`INVALID_STATE`/409 guidance to wait, cancel, or resume. This prevents two
primary-thread mutations from racing silently.
Migration `012_active_agent_turn_uniqueness` backs the check with a partial
unique index over active run states so concurrent API requests cannot create
two active turns after both application checks pass.

The deterministic local initialization turn is treated as thread setup rather
than optional agent work: it does not consume the project’s optional work
budget, so a newly created project with a deliberately small budget can still
accept its first user turn. Normal user turns remain subject to per-run and
workspace budget enforcement.

The local deterministic adapter writes a bounded, workspace/project/thread
scoped JSON checkpoint at run start and terminal/interruption boundaries. It
contains execution metadata only; request/source text and canonical content do
not move into checkpoints. Production Deep Agents uses the configured
LangGraph Postgres checkpointer instead.

The configured Deep Agents runtime uses the same project-bound service context
for snapshot, selected-source retrieval/passage reads, typed content reads,
approved memory, pinned skill metadata, deterministic validation, and
proposal-only patch tools. Its built-in delegation path is limited to named
`source-researcher`, `citation-auditor`, and `module-writer` specialists; shell,
filesystem, SQL, network, credential, and arbitrary object-storage tools are
excluded by the provider harness profile.
