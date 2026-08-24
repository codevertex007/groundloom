# Reliability test plan

Inject failure at every durable boundary: before/after domain commit, outbox publish, checkpoint, SSE broadcast, subagent completion, ingestion stage, render store, approval resolution, and signed-download creation. Kill processes, duplicate deliveries, reorder safe internal events, expire leases, throttle providers, and simulate storage/database reconnects.

Assert no unauthorized/duplicate canonical effect, correct terminal/retry state, replayable progress, preserved proposal/partial results, bounded retries, cancellation responsiveness, and operator-visible diagnostics. Run backup/restore with checksum/count and sampled semantic verification, including checkpoints and object references.
