# Agent runs and streaming component

Owns agent threads, runs, durable public events, run steps/projections, todos, approvals, errors, cancellation, and user messages. Checkpoints remain runtime-owned but correlate by stable thread/run IDs.

Commands: create/send message, cancel, resume/approve, retry eligible failed scope. Queries: thread transcript view, run status, event replay, todos/steps. Persist public events with monotonically increasing per-run sequence through outbox; SSE may reconnect from last sequence.

Required tests: double submit, serialization policy, replay dedupe/order, API/worker restart, cancellation timing, approval expiry/resume, dangling tool call recovery, redaction, event schema compatibility, and no checkpoint leakage in DTOs.
