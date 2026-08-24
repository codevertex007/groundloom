# Database migration runbook

Before deploy: review migration/locks/data volume, test empty and previous snapshot, back up, verify compatible application sequence, define abort criteria. Prefer expand → backfill/verify → switch → contract in a later release.

During deploy: run `backend/scripts/migrate.py` with
`GROUNDLOOM_MIGRATION_DATABASE_URL` / the dedicated `groundloom_migrator` role,
then verify constraints, counts, checkpoint/outbox compatibility, and policy
grants. When `checkpoint_backend=postgres`, the same migrator process initializes
the LangGraph checkpoint schema; runtime workers do not run checkpoint DDL.
Record version and duration. On failure stop rollout; do not blindly
rerun non-idempotent migration. Database rollback is not assumed—use forward
repair or tested restore according to incident decision.

The local fresh-install sequence can be checked with:

```powershell
python backend/scripts/verify_migrations.py
```

It does not claim compatibility with an older production snapshot; that
rehearsal requires a disposable Postgres instance and a prior-release fixture.
