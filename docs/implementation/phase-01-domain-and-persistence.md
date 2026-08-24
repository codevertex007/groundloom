# Phase 01 — Domain and persistence

## Checklist

- [x] `IMPL-01-001` Identity/workspace/membership models, authorization service, audit. Local adapter evidence.
- [x] `IMPL-01-002` Project/configuration-version aggregates, status events, repositories/services.
- [x] `IMPL-01-003` Run/thread/public-event/approval/idempotency/outbox domain records.
- [x] `IMPL-01-004` Typed content/version/proposal schema foundations without generation.
- [x] `IMPL-01-005` API DTOs/endpoints for project grid/create/detail and event replay.
- [x] `IMPL-01-006` Database constraints, indexes, and migrations; PostgreSQL/RLS evidence remains open.
- [x] `IMPL-01-007` Transactional outbox publisher and idempotent delivery seam.
- [x] `IMPL-01-008` Cross-tenant, concurrency, audit, migration, and replay integration tests locally.

## Exit gate
Local gate passes for tenant-safe project lifecycle, ordered replay, restart-safe idempotency, and OpenAPI. Real Postgres/RLS and restart integration evidence remain required before production sign-off.
