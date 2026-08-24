# Model provider failure runbook

Detect elevated timeout/rate/error/schema failure/cost/quality regression by provider/model profile. Pause new costly runs if needed while preserving reads, review, accepted-content operations, and deterministic exports.

Use bounded retries/backoff. Switch to an evaluated compatible fallback only through configuration/feature control and record actual profile; never silently downgrade critical capability. Preserve checkpoint/proposal state, explain waiting/failure to users, and resume safely. After recovery compare traces, costs, and trajectory quality before full traffic.
