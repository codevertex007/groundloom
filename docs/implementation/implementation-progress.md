# Groundloom implementation progress

This file is the live execution record for the autonomous implementation. It is updated with each validated vertical slice; a phase is only marked complete when its documented exit gate has evidence.

## Scope and governing requirements

The implementation covers FR-PROJECT-001..003, FR-SOURCE-001..003, FR-SKILL-001..002, FR-AGENT-001..002, FR-CONTENT-001..005, FR-QUALITY-001, FR-EXPORT-001, FR-AUDIT-001, UI-STATE-001..002, UI-RUN-001..002, UI-PATCH-001..002, UI-CITE-001, UI-A11Y-001, the NFR reliability/performance/security/cost targets, and the ARCH/DATA/SEC/API/EVT/TOOL invariants in the normative documents.

Non-goals remain general web crawling, real-time CRDT collaboration, arbitrary shell access, autonomous publication, model training, and unrelated workflow automation.

## Execution status

| Phase | Status | Evidence / next action |
|---|---|---|
| 00 Repository and contracts | completed-local | Backend tests, ruff, mypy, docs validator, Vite build, and browser smoke passed on 2026-08-24. |
| 01 Domain and persistence | completed-local | Tenant-safe SQLAlchemy domain, lifecycle, runs/events/outbox/audit/content foundations, transaction-scoped tenant context, and API vertical tests passed locally; live Postgres/RLS role evidence remains a release gate. |
| 02 Source ingestion and retrieval | completed-local | Immutable PDF/DOCX/TXT/MD upload and revision lineage, parsing, normalized blocks/chunks, scoped lexical retrieval, passage navigation, prompt-injection signals, durable leased jobs, explicit idempotent derived-index rebuild, idempotent replay, and worker entrypoints are implemented and tested locally; vector embedding remains an external adapter. |
| 03 Primary agent foundation | completed-local | One persistent project thread, adaptive deterministic local runtime, bounded local execution checkpoints, local direct/delegated trajectory tests, durable todos/events, checkpoint seam, SSE replay, cancellation, pinned optional Deep Agents/Postgres adapter, provider safety boundary, approval interrupts, redacted run usage/budget metadata, and leased staging/production agent-worker dispatch are implemented; live provider/recovery evidence is deployment work. |
| 04 Skills, memory, and subagents | completed-local | Versioned skill validation/publication, draft-only skill-author endpoint, scoped redacted memory, bounded delegated-task records with retry/reconciliation, a leased delegated-task worker, and proposal-only tool registry are implemented and tested. |
| 05 Content generation and review | completed-local | Typed immutable content/outline versions, cited proposals, deterministic validation, Accept/Reject, optimistic conflict handling, provenance, durable plan approval, same-thread continuation, and rejection safety are implemented and tested. |
| 06 Quality, evaluation, and export | completed-local | Deterministic validators, versioned rubric/baseline runner, redacted evaluation observation adapter, validation findings, idempotent PDF/DOCX/Markdown/HTML export, and preview/download are implemented; export now has a durable leased worker with explicit local inline mode; model semantic evaluator integration remains external-provider work. |
| 07 Frontend integration | completed-local | Reference-informed React/Vite UI uses a shared API client, durable SSE replay/reconnect with connection state, connected typed workspace Settings persistence, native API/UI contract tests (5 passed), actual React component-rendering tests (3 passed), Playwright E2E/accessibility tests (4 passed), and real API contracts; browser smoke covers create → generate → review → accept, source upload/evidence selection, citation navigation, settings, and command palette. Automated visual baselines remain release work. |
| 08 Security, reliability, and operations | in-progress | Signed runtime identity, parser/path safety, tenant/tool-scope tests, bounded retries, leased-worker replay, checksum-backed local backup/restore, synthetic retrieval benchmark, redaction, alerts, and CI checks exist; Postgres/RLS, production restore/load, sandbox, and incident exercises remain. |
| 09 Production readiness | blocked-external-evidence | Local release is runnable and validated. Production sign-off still requires installed/pinned Deep Agents, Postgres/pgvector, object storage, identity, telemetry, backup/restore, load, and rollback evidence. |

## Initial requirement-to-slice map

| Slice | Requirements | Planned proof |
|---|---|---|
| Contract/runtime foundation | API-*, EVT-*, SEC-AUTH-001..006, NFR-REL-001..004 | OpenAPI/schema tests, config safety tests, health/error tests, docs validation |
| Tenant-safe domain | FR-PROJECT-001..003, FR-AUDIT-001, DATA-*, OPS-* | Repository/service integration and cross-tenant tests |
| Sources/retrieval | FR-SOURCE-001..003, TOOL-RET-001..002 | Parser, lineage, scope, replay, and retrieval tests |
| Agent harness | FR-AGENT-001..002, TOOL-*, AGENT-* | trajectory, interruption, replay, prohibited-call tests |
| Content/review | FR-CONTENT-001..005 | deterministic proposal/accept/reject/conflict tests |
| Quality/export | FR-QUALITY-001, FR-EXPORT-001 | validator, artifact idempotency, download/auth tests |
| UI | UI-* and acceptance journeys J1..J6 | component, accessibility, reconnect, and browser tests |
| Hardening/release | NFR-*, SEC-*, OPS-* | security, reliability, load, migration, backup/restore evidence |

## Decisions and deviations

- Use a modular FastAPI/SQLAlchemy monolith with Postgres-compatible schemas and a SQLite local/test adapter so the application remains runnable without production credentials. Production mode refuses SQLite and in-memory checkpoint/object storage.
- Use a deterministic local model adapter by default for tests/local development; provider adapters are configured explicitly and never pretend to be production success.
- Configure the S3-compatible adapter with explicit connect/read timeouts and bounded SDK retries; all provider failures are mapped to redacted typed dependency errors.
- Use PDF/DOCX/TXT source types and PDF/DOCX exports per the accepted defaults in `assumptions-risks-open-questions.md`.
- The UI reference extraction is temporary and excluded from version control; the archive remains the comparison source.

## Evidence log

| Date | Phase/slice | Evidence |
|---|---|---|
| 2026-08-24 | Establish source of truth | Read root contract, README/docs index, product, architecture, roadmap, dependency map, checklist, release gates, governance risks, phase documents, contracts, components, Deep Agents specifications, and UI archive inventory. |
| 2026-08-25 | Provider/jobs/evaluation hardening | `python -m pytest -q` passed (18 tests); Ruff and mypy passed; deterministic evaluation runner passed; durable ingestion lease/replay, path-safe object storage, production configuration, and optional provider adapter tests passed. |
| 2026-08-25 | Security/reliability hardening | `python -m pytest -q` passed (27 tests plus one optional-provider skip); signed identity rejects missing/tampered bearer context and unsafe production configuration; configured provider failure is retryable and never local success; MIME-spoofed DOCX failure persists; local backup manifest verifies; `benchmark_local.py --requests 20` reported a synthetic p95; parser, database, and benchmark cleanup paths were exercised. |
| 2026-08-25 | Runtime identity and UI reconnect hardening | Staging/production contexts now require signed bearer identity; local frontend SSE replay reconnects with `Last-Event-ID` and displays connection state; frontend build and backend gates remain green. |
| 2026-08-25 | Isolated provider adapter verification | Optional extras installed cleanly in a disposable venv; fake-model Deep Agents graph compile passed for a bounded specialist subagent and the Groundloom runtime factory compiled its scoped tool/subagent harness; Langfuse adapter outage probe remained bounded and did not touch product state; live Postgres/S3/provider credentials remain unavailable. |
| 2026-08-25 | Export, retention, derived-index, and delegation worker slice | Added migrations 003-005, durable export leases/worker, project deletion request/status API, legal-hold policy seam, scoped unshared source/object/checkpoint cleanup, explicit derived lexical-index rebuild API/worker, queued-export polling, leased delegated-task retry consumption, audit/outbox completion, and focused worker tests; the subsequent full backend suite passed 32 tests with one optional-provider skip, frontend API tests 3 passed, frontend build passed, and docs validation passed for 166 documents. |
| 2026-08-25 | Approval and usage slice | Added migration 006, durable plan approval records and events, scoped approval resolution with same-thread continuation/rejection safety, and redacted per-run usage/budget metadata; focused approval test passed. |
| 2026-08-25 | Workspace preferences slice | Added migration 007, typed/audited/idempotent workspace preferences, project pinning with explicit-default precedence, connected Settings UI, and API coverage for persistence/replay/audit-facing behavior. |
| 2026-08-25 | Agent worker slice | Added migration 008, durable AgentRun leases/attempts, staging/production queue dispatch, a real `agent_worker.py` loop, and local worker-mode coverage while preserving inline deterministic development execution. |
| 2026-08-25 | Operational controls slice | Added migrations 009-010, worker heartbeats and bounded readiness/health snapshots, workspace daily token/cost budgets with durable waiting state, provider outage redaction/classification, and S3/Langfuse adapter failure tests; full backend suite passed 38 tests with one optional-provider skip, Ruff/mypy/migration verification passed. |
| 2026-08-25 | Storage adapter hardening | Added explicit S3 connect/read timeout and bounded retry configuration; put/get/head/delete failures now share the typed dependency boundary and focused adapter tests cover write/delete redaction. |
| 2026-08-25 | Durable run controls | Connected the canvas Copilot panel to durable run status plus cancel/resume commands; added staging-shaped cancellation replay coverage and refreshed the browser/API traceability evidence. |
| 2026-08-25 | Final local audit | Deterministic eval reported 1 pass plus 1 intentional needs-revision case; local retrieval benchmark reported p50 6.082 ms/p95 9.316 ms over 20 requests; migrations 001-012 verified and the working tree remains clean after checkpointing. |
| 2026-08-25 | PostgreSQL tenant isolation slice | Added migrations 011 and 013 for forced RLS policies over workspace-owned tables and a dedicated `groundloom_worker` database-role boundary, plus transaction-local context propagation across API commits; ADR-024, security architecture, configuration contract, and traceability were updated. Live role grants/policy execution remain a release gate. |
| 2026-08-25 | Primary-thread serialization slice | Enforced one active mutation turn per project with idempotent same-key replay, a partial unique index, and typed 409 conflict guidance for concurrent requests; added API coverage and updated the run/event contract. |
| 2026-08-25 | Browser E2E slice | Added Playwright web-server orchestration with isolated SQLite/object-store adapters and axe scanning; 3 browser tests passed for project → collaborator → proposal → accept, settings persistence/command-palette navigation, and serious/critical accessibility violations. Visual baselines remain intentionally environment-specific. |
| 2026-08-25 | Frontend supply-chain hardening | Upgraded Vite to the Node-18-compatible patched 6.4.3 line; full `npm audit --audit-level=high` and production-only audit both report zero vulnerabilities. |
| 2026-08-25 | Current local release audit | Backend 42 tests passed with two optional-provider skips in the default environment; the isolated pinned-provider probe passed both optional tests. Frontend native 5, component 3, and Playwright 4 tests passed, including source upload/evidence selection/citation navigation; build, Ruff, mypy, migration verification, docs validation, and npm audits passed. Retrieval benchmark reported p50 9.544 ms/p95 46.369 ms over 20 requests. `pip check` remains red only for the unrelated global Streamlit/protobuf conflict. |
