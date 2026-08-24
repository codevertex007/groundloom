# Local release-candidate evidence

This record is for the credential-free local adapter and is not a production
sign-off. It was refreshed on 2026-08-25 from the repository root.

| Gate | Command/evidence | Result |
|---|---|---|
| Backend unit/contract/security | `python -m pytest -q` | 31 passed; one optional-provider test skips when extras are absent |
| Python lint | `python -m ruff check backend/app backend/tests backend/scripts` | Passed |
| Python types | `python -m mypy backend/app` | Passed; 20 source files |
| Documentation/traceability | `python backend/scripts/validate_docs.py` | Passed; 165 markdown documents |
| Frontend build | `cd frontend; npm run build` | Passed |
| Frontend API-client tests | `cd frontend; npm test` | 3 passed: typed retryable errors/correlation, SSE reconnect cursor/offline behavior, and queued export polling |
| Frontend dependency audit | `cd frontend; npm audit --omit=dev` | 0 vulnerabilities |
| Python environment audit | `python -m pip check` | Existing environment conflict: `streamlit 1.43.1` requires `protobuf<6`, installed environment has `protobuf 6.31.1`; unrelated to Groundloom's declared dependencies and should be resolved in a clean release environment. |
| Optional provider API contract | Isolated probe venv with `.[agent,postgres,storage,observability]`; `pytest backend/tests/test_optional_provider_contracts.py -q` | Pinned packages installed cleanly; fake-model `CompiledStateGraph` compile passed; Langfuse adapter construction/flush was exercised against an intentionally unavailable endpoint and failed only as bounded telemetry export, not product state. |
| Deterministic evaluation | `python backend/scripts/run_evals.py` | 1 pass / 1 intentional needs-revision regression case; redacted `evaluation.completed` observation emitted |
| Retrieval envelope | `python backend/scripts/benchmark_local.py --requests 20` | Synthetic SQLite/filesystem p50/p95 emitted; not a production SLO |
| Migration | `python backend/scripts/migrate.py`, `python backend/scripts/verify_migrations.py`, and migration status query | `001_initial_domain_schema`, `002_ingestion_jobs_and_provider_adapters`, `003_retention_deletion_and_export_leases`, `004_index_rebuild_jobs` |
| Export/retention workers | `backend/tests/test_retention_and_export_workers.py` | Staging-shaped queued export completes through a leased worker; project deletion removes unshared source artifacts and canonical records with durable audit status |
| Browser journey | Existing browser smoke evidence | Create → source-grounded draft → review → accept passed |

## Not locally executable

Live Deep Agents/model-provider invocation, Postgres/pgvector and Postgres
checkpoint integration, S3-compatible storage, Langfuse delivery, external
identity, OCR, production worker concurrency, encrypted backup/restore,
container sandboxing, staging soak/rollback, and release-owner approval require
external services or credentials. The application fails clearly or rejects
unsafe production configuration when these are absent; no local result is
represented as production evidence.

The Docker CLI is installed, but the Docker Desktop Linux daemon was not
reachable during this run (`docker compose up -d` could not connect to the
named pipe), so the disposable Postgres/MinIO compose services were not started.
