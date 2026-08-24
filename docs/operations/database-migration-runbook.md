# Database migration runbook

Before deploy: review migration/locks/data volume, test empty and previous snapshot, back up, verify compatible application sequence, define abort criteria. Prefer expand → backfill/verify → switch → contract in a later release.

During deploy: apply with monitored timeout, record version/duration, verify constraints/counts/checkpoint/outbox compatibility. On failure stop rollout; do not blindly rerun non-idempotent migration. Database rollback is not assumed—use forward repair or tested restore according to incident decision.
