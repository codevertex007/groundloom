# ADR-015: Deterministic workflows for ingestion and export

**Status:** Accepted

## Decision
Scanning/parsing/indexing, rendering, cleanup, and scheduled infrastructure use explicit idempotent workflows/workers. The primary agent may request/observe them but does not implement their algorithms.

## Consequences
Clear retry/progress semantics and predictable artifacts; separate worker operations are required.

## Validation
Stage replay, job lease death, duplicate request, cancellation, and exact-version tests.
