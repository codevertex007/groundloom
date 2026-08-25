# ADR-014: Durable SSE through transactional outbox and replay

**Status:** Accepted

## Decision
Persist normalized public events/outbox before broadcast and replay by monotonic per-run sequence.

Provider-backed primary-agent runs normalize the verified LangGraph
`messages`/`updates` stream into bounded public progress, tool, and subagent
events before persistence. The normalization boundary excludes model text,
tool arguments, source content, and hidden reasoning; cancellation is checked
between stream chunks against the durable run flag.

## Consequences
Some latency/storage overhead; reconnect and worker/API restart no longer lose product progress.

## Validation
Ordering, duplicate suppression, reconnect, process death, schema compatibility, and redaction tests.
