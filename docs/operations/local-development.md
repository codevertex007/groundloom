# Local development

The credential-free local command starts the SQLite/filesystem adapters, API,
and frontend. A bounded ingestion worker pass is available with
`python backend/scripts/ingestion_worker.py --once`; agent and export worker
entrypoints remain independently runnable deployment seams. The optional
`agent`, `storage`, and `observability` groups activate the verified provider
adapters. Never require production credentials or real tenant data for local
tests.

The export worker can be run with python backend/scripts/export_worker.py and
the retention worker with python backend/scripts/retention_worker.py. The
derived lexical index worker can be run with python
backend/scripts/index_worker.py.
The delegated specialist worker can be run with python
backend/scripts/delegated_worker.py.
The durable primary-agent worker can be run with python
backend/scripts/agent_worker.py --once.
`GROUNDLOOM_RETRIEVAL_INDEX_BACKEND=auto` keeps SQLite on the local JSON
index and selects the pgvector derived table for PostgreSQL. The deployment-
shaped Postgres stack requires migration 015 and an installed pgvector
extension before source ingestion or semantic search is exercised.
The bundled MinIO emulator does not provide the production KMS/SSE setup, so
deployment-shaped local tests use `GROUNDLOOM_OBJECT_STORE_SSE_MODE=none`;
production startup rejects that mode and requires AES-256 or KMS encryption.
Image-only PDFs enter the `ocr` ingestion stage. Credential-free local mode
fails those versions with a typed provider-configuration error; to exercise
OCR success, configure `GROUNDLOOM_OCR_PROVIDER=http` with a local or staging
sidecar that implements the bounded `/ocr` contract documented in the
configuration contract.
The outbox publisher requires an explicit sink and can be exercised with
`GROUNDLOOM_OUTBOX_DELIVERY_PROVIDER=webhook`,
`GROUNDLOOM_OUTBOX_DELIVERY_URL=<local-relay>`, and
`python backend/scripts/outbox_worker.py --once`; with the default disabled
sink it fails clearly and never marks events delivered.
development adapter renders exports inline by default; set
GROUNDLOOM_EXPORT_INLINE_LOCAL=false to exercise the durable export worker.

Deployment-shaped workers all share the dedicated worker-session helper. In
production they use `GROUNDLOOM_WORKER_DATABASE_URL`; schema changes are run
separately with `GROUNDLOOM_MIGRATION_DATABASE_URL` and are never applied by an
API or worker process.

The local default keeps the deterministic agent inline. To exercise the durable
agent path without external credentials, set
`GROUNDLOOM_AGENT_INLINE_LOCAL=false` and run the agent worker with the local
provider; staging/production always require the durable worker path.

The frontend E2E suite starts isolated local backend and frontend processes. From
`frontend`, run `npx playwright install chromium` once and then
`npm run test:e2e`.

Fresh setup, reset of local disposable services, migrations, tests, and UI smoke must be reproducible on supported developer platforms. Production mode rejects local bypasses. Record exact package/runtime versions and troubleshooting for ports, migrations, worker leases, and callback URLs.
