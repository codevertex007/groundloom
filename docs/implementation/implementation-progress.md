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
| 02 Source ingestion and retrieval | completed-local | Immutable PDF/DOCX/TXT/MD upload and revision lineage, parsing, normalized blocks/chunks, scoped lexical retrieval, passage navigation, and prompt-injection signals are implemented and tested locally. |
| 03 Primary agent foundation | completed-local | One persistent project thread, adaptive deterministic local runtime, durable todos/events, checkpoint seam, SSE replay, cancellation, and provider safety boundary are implemented; verified Deep Agents/Postgres adapter is deployment work. |
| 04 Skills, memory, and subagents | completed-local | Versioned skill validation/publication, scoped redacted memory, bounded delegated-task records, and proposal-only tool registry are implemented and tested. |
| 05 Content generation and review | completed-local | Typed immutable content/outline versions, cited proposals, deterministic validation, Accept/Reject, optimistic conflict handling, and provenance are implemented and tested. |
| 06 Quality, evaluation, and export | completed-local | Deterministic validators, validation findings, idempotent PDF/DOCX/Markdown/HTML export, preview/download, and redacted telemetry seam are implemented; semantic evaluator integration remains external-provider work. |
| 07 Frontend integration | completed-local | Reference-informed React/Vite UI is wired to real API contracts; browser smoke completed create → generate → review → accept on 2026-08-24. |
| 08 Security, reliability, and operations | in-progress | Tenant/auth/tool-scope tests, path-safe checkpoints, production configuration guards, outbox delivery seam, redaction, and CI checks exist; Postgres, backup/restore, load, sandbox, and incident exercises remain. |
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
| 2026-08-25 | Local phases 01-07 vertical slice | `python -m pytest backend/tests -q` passed (13 tests); `python -m ruff check backend/app backend/tests backend/scripts` passed; `python -m mypy backend/app --ignore-missing-imports` passed; `python backend/scripts/validate_docs.py` passed; `npm run build` passed from `frontend`; browser smoke created/accepted a project draft; SSE replay, source revision lineage, scoped memory, checkpoint, outbox, telemetry redaction, and project-create idempotency tests passed. |
