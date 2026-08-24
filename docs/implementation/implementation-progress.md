# Groundloom implementation progress

This file is the live execution record for the autonomous implementation. It is updated with each validated vertical slice; a phase is only marked complete when its documented exit gate has evidence.

## Scope and governing requirements

The implementation covers FR-PROJECT-001..003, FR-SOURCE-001..003, FR-SKILL-001..002, FR-AGENT-001..002, FR-CONTENT-001..005, FR-QUALITY-001, FR-EXPORT-001, FR-AUDIT-001, UI-STATE-001..002, UI-RUN-001..002, UI-PATCH-001..002, UI-CITE-001, UI-A11Y-001, the NFR reliability/performance/security/cost targets, and the ARCH/DATA/SEC/API/EVT/TOOL invariants in the normative documents.

Non-goals remain general web crawling, real-time CRDT collaboration, arbitrary shell access, autonomous publication, model training, and unrelated workflow automation.

## Execution status

| Phase | Status | Evidence / next action |
|---|---|---|
| 00 Repository and contracts | completed-local | Backend tests, ruff, mypy, docs validator, Vite build, and browser smoke passed on 2026-08-24. |
| 01 Domain and persistence | completed-local | Tenant-safe SQLAlchemy domain, lifecycle, runs/events/outbox/audit/content foundations and API vertical tests passed locally; real Postgres/RLS evidence remains a release gate. |
| 02 Source ingestion and retrieval | completed-local | Immutable PDF/DOCX/TXT/MD upload and revision lineage, parsing, normalized blocks/chunks, scoped lexical retrieval, passage navigation, prompt-injection signals, durable leased jobs, idempotent replay, and worker entrypoint are implemented and tested locally. |
| 03 Primary agent foundation | completed-local | One persistent project thread, adaptive deterministic local runtime, durable todos/events, checkpoint seam, SSE replay, cancellation, pinned optional Deep Agents/Postgres adapter, and provider safety boundary are implemented; live provider/recovery evidence is deployment work. |
| 04 Skills, memory, and subagents | completed-local | Versioned skill validation/publication, scoped redacted memory, bounded delegated-task records, and proposal-only tool registry are implemented and tested. |
| 05 Content generation and review | completed-local | Typed immutable content/outline versions, cited proposals, deterministic validation, Accept/Reject, optimistic conflict handling, and provenance are implemented and tested. |
| 06 Quality, evaluation, and export | completed-local | Deterministic validators, versioned rubric protocol/baseline runner, validation findings, idempotent PDF/DOCX/Markdown/HTML export, preview/download, and redacted telemetry seam are implemented; model semantic evaluator integration remains external-provider work. |
| 07 Frontend integration | completed-local | Reference-informed React/Vite UI uses a shared API client, durable SSE replay/reconnect with connection state, and real API contracts; browser smoke completed create → generate → review → accept on 2026-08-24. Automated component/a11y/e2e evidence remains release work. |
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
- Use PDF/DOCX/TXT source types and PDF/DOCX exports per the accepted defaults in `assumptions-risks-open-questions.md`.
- The UI reference extraction is temporary and excluded from version control; the archive remains the comparison source.

## Evidence log

| Date | Phase/slice | Evidence |
|---|---|---|
| 2026-08-24 | Establish source of truth | Read root contract, README/docs index, product, architecture, roadmap, dependency map, checklist, release gates, governance risks, phase documents, contracts, components, Deep Agents specifications, and UI archive inventory. |
| 2026-08-25 | Provider/jobs/evaluation hardening | `python -m pytest -q` passed (18 tests); Ruff and mypy passed; deterministic evaluation runner passed; durable ingestion lease/replay, path-safe object storage, production configuration, and optional provider adapter tests passed. |
| 2026-08-25 | Security/reliability hardening | `python -m pytest -q` passed (22 tests); signed identity rejects missing/tampered bearer context and unsafe production configuration; MIME-spoofed DOCX failure persists; local backup manifest verifies; `benchmark_local.py --requests 20` reported a synthetic p95; parser, database, and benchmark cleanup paths were exercised. |
| 2026-08-25 | Runtime identity and UI reconnect hardening | Staging/production contexts now require signed bearer identity; local frontend SSE replay reconnects with `Last-Event-ID` and displays connection state; frontend build and backend gates remain green. |
