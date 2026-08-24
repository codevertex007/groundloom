# Database migration runbook

Before deploy: review migration/locks/data volume, test empty and previous snapshot, back up, verify compatible application sequence, define abort criteria. Prefer expand → backfill/verify → switch → contract in a later release.

During deploy: apply with monitored timeout, record version/duration, verify constraints/counts/checkpoint/outbox compatibility. On failure stop rollout; do not blindly rerun non-idempotent migration. Database rollback is not assumed—use forward repair or tested restore according to incident decision.

The local fresh-install sequence can be checked with:

```powershell
python backend/scripts/verify_migrations.py
```

It does not claim compatibility with an older production snapshot; that
rehearsal requires a disposable Postgres instance and a prior-release fixture.
