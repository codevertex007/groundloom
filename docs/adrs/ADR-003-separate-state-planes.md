# ADR-003: Separate product, execution, artifact, scratch, and derived state

**Status:** Accepted

## Decision
Postgres domain tables own product state; Postgres checkpoints own execution; object storage owns binaries/artifacts; Deep Agents backends own scratch; retrieval indexes are derived; Langfuse owns telemetry.

## Consequences
Cross-plane operations need IDs, idempotency, outbox, and recovery logic. UI cannot use checkpoints as a database.

## Validation
Recovery/rebuild tests and code-boundary review verify each state category has one authority.
