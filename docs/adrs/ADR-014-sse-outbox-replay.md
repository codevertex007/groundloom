# ADR-014: Durable SSE through transactional outbox and replay

**Status:** Accepted

## Decision
Persist normalized public events/outbox before broadcast and replay by monotonic per-run sequence.

## Consequences
Some latency/storage overhead; reconnect and worker/API restart no longer lose product progress.

## Validation
Ordering, duplicate suppression, reconnect, process death, schema compatibility, and redaction tests.
