# Runtime topology

Initial deployable processes:

- Web UI static/server runtime.
- FastAPI API/BFF for auth, commands, queries, uploads, SSE, and DTOs.
- Agent workers claiming leased queued runs and executing/resuming compiled Deep Agents with Postgres checkpoints.
- Ingestion workers for scanning, parsing/OCR, normalization, chunking, embedding, indexing.
- Export workers for deterministic rendering and artifact storage.
- Optional maintenance worker for cleanup, retention, and scheduled quality jobs.
- Postgres/pgvector, object storage, and Langfuse.

The code begins as a modular monolith with shared domain packages and separate process entry points. A component may be extracted only after measurable scaling, isolation, ownership, or deployment pressure and an ADR.

Agent/API processes MUST be horizontally safe: no correctness depends on process memory. Job claiming uses durable leases; SSE uses persisted events; checkpoint resume may occur on another worker.
Interactive local/test runs may execute inline for a fast credential-free loop.
Staging and production dispatch agent runs to `backend/scripts/agent_worker.py`
so model latency does not occupy API worker capacity; the worker records leases,
attempts, actor context, and terminal/requeue state durably.
