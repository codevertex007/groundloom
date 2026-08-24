# ADR-015: Deterministic workflows for ingestion and export

**Status:** Accepted

## Decision
Scanning/parsing/indexing, rendering, cleanup, and scheduled infrastructure use explicit idempotent workflows/workers. The primary agent may request/observe them but does not implement their algorithms.

## Consequences
Clear retry/progress semantics and predictable artifacts; separate worker operations are required.

Groundloom implements this boundary with durable leased ingestion, export, and
retention/deletion processors. Local development may execute a bounded inline
export pass for usability, but the same processor is used by the standalone
worker and production never enables the inline shortcut. Project deletion
records a durable request, tombstones the project before cleanup, deletes only
unshared source artifacts, and remains retryable after partial failure.

## Validation
Stage replay, job lease death, duplicate request, cancellation, and exact-version tests.
