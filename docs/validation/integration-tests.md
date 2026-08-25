# Integration test catalog

Run against real ephemeral Postgres/pgvector and object storage. Cover migrations from empty/previous release, transaction rollback, unique/FK/RLS constraints, outbox commit/publish/replay, checkpoints/interrupt resume, job leases, object upload/finalize, derived-index rebuild, signed download, and telemetry adapter outage.

Failure injection kills API/agent/worker after domain commit but before checkpoint, after checkpoint but before public broadcast, mid-parser/render, and during provider calls. Assert canonical state, retryability, no duplicates, intelligible status, and cleanup eligibility.

Cross-tenant integration tests invoke repositories/services/tools directly as well as APIs.

The repeatable CI deployment-shaped job starts the repository's disposable
Postgres/pgvector and MinIO stack, runs migrations and LangGraph checkpoint
schema setup through `groundloom_migrator`, and executes
`backend/tests/test_postgres_deployment_integration.py` with the API/worker
role URLs. It intentionally uses local-only credentials and
`GROUNDLOOM_OBJECT_STORE_SSE_MODE=none`; production startup still requires
AES-256 or KMS object-storage encryption and a real encrypted backup/restore
rehearsal.
