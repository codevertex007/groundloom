# Local release-candidate evidence

This record is for the credential-free local adapter and is not a production
sign-off. It was refreshed on 2026-08-25 from the repository root.

| Gate | Command/evidence | Result |
|---|---|---|
| Backend unit/contract/security | `python -m pytest -q -rA` | 37 passed; one optional-provider test skips when extras are absent |
| Python lint | `python -m ruff check backend/app backend/tests backend/scripts` | Passed |
| Python types | `python -m mypy backend/app backend/scripts` | Passed; 32 source files |
| Documentation/traceability | `python backend/scripts/validate_docs.py` | Passed; refreshed through migration 010, worker health, budget, and provider outage contracts |
| Frontend build | `cd frontend; npm run build` | Passed |
| Frontend API/UI contract tests | `cd frontend; npm test` | 5 passed: typed retryable errors/correlation, SSE reconnect cursor/offline behavior, queued export polling, reference-surface/mutation presence, and interactive accessibility semantics |
| Frontend E2E/accessibility | `cd frontend; npx playwright install chromium; npm run test:e2e` | 3 Playwright tests passed: real local backend/frontend startup, project → collaborator → proposal → accept, settings persistence, command-palette navigation, and axe serious/critical accessibility scan; committed visual baselines are intentionally not claimed |
| Frontend dependency audit | `cd frontend; npm audit --omit=dev && npm audit --audit-level=high` | 0 vulnerabilities in production and development dependency trees |
| Python environment audit | `python -m pip check` | Existing environment conflict: `streamlit 1.43.1` requires `protobuf<6`, installed environment has `protobuf 6.31.1`; unrelated to Groundloom's declared dependencies and should be resolved in a clean release environment. |
| Optional provider API contract | Isolated probe venv with `.[agent,postgres,storage,observability]`; `pytest backend/tests/test_optional_provider_contracts.py -q` | Pinned packages installed cleanly; fake-model `CompiledStateGraph` compile passed; Langfuse adapter construction/flush was exercised against an intentionally unavailable endpoint and failed only as bounded telemetry export, not product state. |
| Deterministic evaluation | `python backend/scripts/run_evals.py` | 1 pass / 1 intentional needs-revision regression case; redacted `evaluation.completed` observation emitted |
| Retrieval envelope | `python backend/scripts/benchmark_local.py --requests 20` | Synthetic SQLite/filesystem p50/p95 emitted; not a production SLO |
| Migration | `python backend/scripts/migrate.py`, `python backend/scripts/verify_migrations.py`, and migration status query | `001_initial_domain_schema` through `010_budget_controls` verified |
| Export/retention workers | `backend/tests/test_retention_and_export_workers.py` | Staging-shaped queued export completes through a leased worker; project deletion removes unshared source artifacts and canonical records with durable audit status |
| Derived-index/delegated workers | `backend/tests/test_index_rebuild_worker.py`, `backend/tests/test_delegation_recovery.py` | Scoped lexical index rebuild and failed delegated-task retry are consumed by bounded leased workers |
| Object-storage adapter boundary | `backend/tests/test_adapters_and_jobs.py::test_external_adapters_classify_outages_without_leaking_provider_errors` | S3-compatible reads, writes, and deletes map provider failures to typed retryable errors; configured SDK timeouts and bounded standard retries are part of the production adapter |
| Browser journey/accessibility | Existing browser smoke plus current DOM inspection | Create → source-grounded draft → review → accept passed; settings dialog close/toggle/export controls and canvas navigation expose accessible names; approval controls are rendered for pending plan requests |

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
