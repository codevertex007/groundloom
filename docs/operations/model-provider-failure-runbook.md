# Model provider failure runbook

Detect elevated timeout/rate/error/schema failure/cost/quality regression by provider/model profile. Pause new costly runs if needed while preserving reads, review, accepted-content operations, and deterministic exports.

Queued staging/production runs are claimed by the durable agent worker. Provider
failures remain retryable within the configured attempt bound, release the lease,
and leave a durable failed/requeue state for operators; the API remains
available for reads, review, and existing exports.

Use bounded retries/backoff. Switch to an evaluated compatible fallback only through configuration/feature control and record actual profile; never silently downgrade critical capability. Preserve checkpoint/proposal state, explain waiting/failure to users, and resume safely. After recovery compare traces, costs, and trajectory quality before full traffic.
