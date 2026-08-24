# Groundloom

Groundloom is a source-grounded knowledge production studio. It uses one persistent primary Deep Agent per project to investigate sources, load skills, plan work, delegate bounded tasks, draft structured content, validate results, repair failures, and collaborate with the user from project setup through export.

This repository pack is an implementation specification for Codex. It intentionally contains documentation and references before application code.

## Start here

1. Read [`AGENTS.md`](AGENTS.md) completely.
2. Read [`docs/README.md`](docs/README.md) for the normative document order.
3. Review [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md).
4. Resolve blocking items in [`docs/governance/assumptions-risks-open-questions.md`](docs/governance/assumptions-risks-open-questions.md).
5. Execute the phases in [`docs/implementation/master-roadmap.md`](docs/implementation/master-roadmap.md).

## Product architecture in one sentence

A persistent central Deep Agent owns the adaptive semantic loop; typed tools, scoped skills, memory, middleware, validation hooks, and specialist subagents form its harness; deterministic services own authorization, canonical persistence, ingestion, rendering, approvals, and external side effects.

## Repository state

This package is specification-first. Empty application directories should not be created merely to resemble the target layout. Codex should introduce code only when a phase document calls for it, together with its required tests, migration, telemetry, and documentation updates.

## Working name

`Groundloom` is a working product/repository name and has not undergone legal trademark clearance.

## Local development

The local adapter runs without production credentials. Python 3.11+ and Node 18+ are supported.

```powershell
python -m pip install -e ".[dev,documents,postgres]"
Copy-Item .env.example .env
$env:PYTHONPATH = "backend"
python backend/scripts/migrate.py
python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The default local identity is `local-user` in `local-workspace`; production mode rejects SQLite, the deterministic model provider, wildcard CORS, and missing auth configuration. Postgres/pgvector and MinIO can be started with `docker compose up -d` for deployment-shaped local testing.

Validation commands:

```powershell
python -m pytest backend/tests -q
python -m ruff check backend/app backend/tests
python -m mypy backend/app --ignore-missing-imports
python backend/scripts/validate_docs.py
cd frontend; npm run build

# Optional disposable local recovery exercise
cd ..
python backend/scripts/backup_local.py backup --database backend/data/groundloom.db --objects backend/data/objects --destination .local-backup
python backend/scripts/backup_local.py restore --database backend/data/restored.db --objects backend/data/restored-objects --destination .local-backup
```
