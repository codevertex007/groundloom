# Local release-candidate evidence

This record is for the credential-free local adapter and is not a production
sign-off. It was refreshed on 2026-08-25 from the repository root.

| Gate | Command/evidence | Result |
|---|---|---|
| Backend unit/contract/security | `python -m pytest backend/tests -q -rA` | 49 passed; two optional-provider tests and three opt-in deployment-integration tests skip in the default local environment; the provider probe passes both optional tests and the disposable Docker run passes all three deployment tests |
| Python lint | `python -m ruff check backend/app backend/tests backend/scripts` | Passed |
| Python types | `python -m mypy backend/app backend/scripts` | Passed; 32 source files |
| Documentation/traceability | `python backend/scripts/validate_docs.py` | Passed; refreshed through migration 014, serialized active-turn, worker health, budget, provider outage, role-bound tenant-RLS, worker-role, migrator-role, and project-key contracts |
| Frontend build | `cd frontend; npm run build` | Passed |
| Frontend API/UI contract tests | `cd frontend; npm test` and `npm run test:components` | 5 native tests plus 3 actual React component-rendering tests passed: typed retryable errors/correlation, SSE reconnect cursor/offline behavior, queued export polling, reference-surface/mutation presence, interactive accessibility semantics, shared header/empty-state rendering, and command-palette route rendering |
| Frontend E2E/accessibility | `cd frontend; npx playwright install chromium; npm run test:e2e` | 10 Playwright tests passed on the pinned Windows Chromium lane: stable projects/sources visual baselines, project → collaborator → proposal → accept/reject, settings persistence, command-palette navigation, plan approval/resume, AI skill draft → validate → publish, immutable repair workflow, dropped-stream reconnect, permission-denied rendering, source upload/readiness, evidence selection, citation-panel navigation, and axe serious/critical accessibility scan; non-Windows CI runs the 9 semantic tests and skips only the pixel baseline test |
| Frontend dependency audit | `cd frontend; npm audit --omit=dev && npm audit --audit-level=high` | 0 vulnerabilities in production and development dependency trees |
| Python environment audit | `python -m pip check` | Existing environment conflict: `streamlit 1.43.1` requires `protobuf<6`, installed environment has `protobuf 6.31.1`; unrelated to Groundloom's declared dependencies and should be resolved in a clean release environment. |
| Optional provider API contract | Isolated probe venv with `.[agent,postgres,storage,observability]`; `pytest backend/tests/test_optional_provider_contracts.py -q` | Pinned packages installed cleanly; fake-model `CompiledStateGraph` compile passed for a bounded specialist subagent, and the Groundloom runtime factory compiled its scoped tool/subagent harness without provider credentials; Langfuse adapter construction/flush was exercised against an intentionally unavailable endpoint and failed only as bounded telemetry export, not product state. |
| Deterministic evaluation | `python backend/scripts/run_evals.py` | 1 pass / 1 intentional needs-revision regression case; redacted `evaluation.completed` observation emitted |
| Retrieval envelope | `python backend/scripts/benchmark_local.py --requests 20` | SQLite/filesystem adapter: p50 6.641 ms, p95 9.791 ms, max 9.791 ms; not a production SLO |
| Migration | `python backend/scripts/migrate.py`, `python backend/scripts/verify_migrations.py`, `docker compose config --quiet`, and `backend/tests/test_postgres_deployment_integration.py` | `001_initial_domain_schema` through `014_project_id_primary_key` verified; disposable Docker Postgres migration passed with API/worker/migrator roles, forced RLS, project-key repair, and LangGraph checkpoint tables; the opt-in deployment integration suite passed 3 tests, including tenant isolation and worker bypass |
| Export/retention workers | `backend/tests/test_retention_and_export_workers.py` | Staging-shaped queued export completes through a leased worker; project deletion removes unshared source artifacts and canonical records with durable audit status |
| Derived-index/delegated workers | `backend/tests/test_index_rebuild_worker.py`, `backend/tests/test_delegation_recovery.py` | Scoped lexical index rebuild and failed delegated-task retry are consumed by bounded leased workers |
| Object-storage adapter boundary | `backend/tests/test_adapters_and_jobs.py::test_external_adapters_classify_outages_without_leaking_provider_errors` | S3-compatible reads, writes, and deletes map provider failures to typed retryable errors; configured SDK timeouts and bounded standard retries are part of the production adapter |
| Browser journey/accessibility | `frontend/e2e/groundloom.spec.js` (10 tests) plus committed `frontend/e2e/groundloom.spec.js-snapshots/` | Project creation, source-grounded draft, review accept/reject, plan approval/resume, AI skill lifecycle and immutable repair, permission-denied rendering, settings, command palette, dropped-stream reconnect, source/citation navigation, two stable visual baselines, and serious/critical axe scan passed |

## External release gates still open

Live Deep Agents/model-provider invocation, Langfuse delivery, external
identity, OCR, production worker concurrency, encrypted backup/restore,
container sandboxing, staging soak/rollback, and release-owner approval require
external services or credentials. The disposable Postgres/pgvector, Postgres
checkpoint, and MinIO/S3-compatible paths were exercised locally; this is
deployment-shaped integration evidence, not production capacity or release
sign-off. The application fails clearly or rejects unsafe production
configuration when required services are absent.

The disposable validation stack was started with `docker compose up -d` on
2026-08-25. `docker compose config --quiet` passed, MinIO initialized the
`groundloom` bucket, and the pinned provider-probe interpreter ran the opt-in
Postgres/S3 suite. The stack uses local-only credentials from
`docker/postgres-init/001-roles.sql` and must not be treated as production
secrets.
