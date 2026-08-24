# ADR-004: Postgres is canonical product state

**Status:** Accepted

## Decision
Use Postgres for tenant/domain records, immutable versions, approvals, jobs, audit, idempotency, outbox, and production checkpoints; pgvector supports initial retrieval.

## Consequences
Schema/migration quality is release-critical. Vector/search data remains rebuildable. Avoid introducing a second canonical operational database.

## Validation
Constraint, migration, backup/restore, replay, and derived-index rebuild tests.
