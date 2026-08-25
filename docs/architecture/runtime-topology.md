# Runtime topology

Initial deployable processes:

- Web UI static/server runtime.
- FastAPI API/BFF for auth, commands, queries, uploads, SSE, and DTOs.
- Agent workers claiming leased queued runs and executing/resuming compiled Deep Agents with Postgres checkpoints.
- Ingestion workers for scanning, parsing/OCR, normalization, chunking, embedding, indexing.
- Export workers for deterministic rendering and artifact storage.
- Outbox publisher workers delivering normalized events to a configured external
  relay; delivery is at-least-once and consumers deduplicate by event ID.
- Optional maintenance worker for cleanup, retention, and scheduled quality jobs.
- Postgres/pgvector, object storage, and Langfuse.

The code begins as a modular monolith with shared domain packages and separate process entry points. A component may be extracted only after measurable scaling, isolation, ownership, or deployment pressure and an ADR.

Agent/API processes MUST be horizontally safe: no correctness depends on process memory. Job claiming uses durable leases; SSE uses persisted events; checkpoint resume may occur on another worker.
Interactive local/test runs may execute inline for a fast credential-free loop.
Staging and production dispatch agent, ingestion, index, delegation, export,
retention, and outbox delivery runs to their durable worker entrypoints so model or parser latency
does not occupy API capacity. Each production worker connects with
`GROUNDLOOM_WORKER_DATABASE_URL` as the dedicated `groundloom_worker` database
role and records leases, attempts, actor context, and terminal/requeue state
durably. `GROUNDLOOM_MIGRATION_DATABASE_URL` is reserved for the migration
process and is never used by an API or worker.

`outbox_worker.py` refuses to start with the disabled local sink. The webhook
adapter sends only bounded normalized event envelopes and a stable event ID;
the sink must be idempotent because retries are at-least-once.
