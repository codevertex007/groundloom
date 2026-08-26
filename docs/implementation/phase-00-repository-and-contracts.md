# Phase 00 — Repository and contracts

## Outcome
Reproducible local repository with enforced boundaries and no product placeholders.

## Checklist

- [x] `IMPL-00-001` Initialize backend/frontend layout, package management, formatting, lint, typing, test runners. Evidence: `pyproject.toml`, `frontend/package.json`, successful pytest/ruff/mypy/Vite build.
- [x] `IMPL-00-002` Add root/package `AGENTS.md` instructions and docs link/ID validation. Evidence: root `AGENTS.md`, `backend/scripts/validate_docs.py`.
- [x] `IMPL-00-003` Configure local Postgres/pgvector and object-storage emulator; no in-memory production defaults. Evidence: `docker-compose.yml`, local filesystem adapter, production settings refusal.
- [x] `IMPL-00-004` Add settings validation and secret-safe logging. Evidence: `backend/app/config.py`, `test_production_refuses_unsafe_defaults`.
- [x] `IMPL-00-005` Create FastAPI skeleton, health taxonomy, correlation/error middleware. Evidence: `backend/app/main.py`, `/health`, typed error handler.
- [x] `IMPL-00-006` Define initial OpenAPI/event/tool schema packages from contracts. Evidence: Pydantic DTOs, normalized event envelope, `test_openapi_contains_contract_boundary`.
- [x] `IMPL-00-007` Add migration/checkpointer/outbox foundations and Langfuse adapter interface/fake. Evidence: SQLAlchemy domain/checkpoint seam, `backend/app/migrations.py`, `OutboxMessage`.
- [x] `IMPL-00-008` Configure CI: format, lint, type, unit, contract, migration, docs checks. Evidence: `.github/workflows/ci.yml`, local validation commands in README.
- [x] `IMPL-00-009` Keep generated caches, build output, local runtime state, and root artifact directories out of version control without masking nested source packages. Evidence: anchored root artifact rules in `.gitignore` and repository hygiene validation.

## Exit gate
Exit evidence: fresh local API and Vite build booted on 2026-08-24; backend tests 6 passed; ruff and mypy passed; frontend `npm run build` passed; browser smoke created a project, generated a proposal, and accepted it; production unsafe-config test passed. CI is configured for the same gates.
