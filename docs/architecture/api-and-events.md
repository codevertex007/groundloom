# API and event architecture

The API uses `/v1`, JSON/Pydantic product DTOs, opaque IDs, request correlation, and idempotency keys for writes. Long agent/job progress uses SSE with `Last-Event-ID`/sequence replay; command responses return resource/run IDs quickly instead of holding connections for complete generation.

Public events contain `event_id`, monotonically increasing run sequence, schema version, workspace/project/run/thread correlation, timestamp, type, and bounded payload. Persist through an outbox before broadcast. Internal model tokens/tool payloads are transformed and redacted; public consumers never depend on LangGraph event names.

Concurrency:

- one active mutation turn per primary project thread;
- read-only queries may queue or execute independently if state-safe;
- concurrent module subagents have explicit ownership;
- content acceptance uses expected base/current version;
- duplicate client submissions resolve by idempotency key.

See `contracts/rest-api-contract.md`, `contracts/sse-event-catalog.md`, and `contracts/error-taxonomy.md`.
