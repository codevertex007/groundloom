# Reliability and recovery

Failure classes: transient provider/rate limit, schema-invalid model output, empty/conflicting retrieval, parser/index failure, optimistic conflict, cancellation, approval timeout, authorization denial, dependency outage, and application defect.

Each class has explicit retryability, backoff, maximum attempts, user message, telemetry severity, and resume behavior. Authorization/policy denial and invalid irreversible operations are never retried as transient errors.

Cancellation is durable and checked before tool calls, between model turns, and by workers/subagents. Partial proposals remain non-canonical. Worker leases expire safely. Checkpoint resume repairs incomplete tool-call histories and reuses idempotent durable effects.

Recovery priorities: prevent unauthorized/duplicate effects; preserve canonical data; produce an intelligible run state; allow targeted resume/retry; clean non-canonical artifacts later. Test process death at every durable boundary.
