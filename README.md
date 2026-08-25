# Groundloom

Groundloom is a source-grounded knowledge production studio. It uses one persistent primary Deep Agent per project to investigate sources, load skills, plan work, delegate bounded tasks, draft structured content, validate results, repair failures, and collaborate with the user from project setup through export.

This repository contains the implemented local vertical system plus the
deployment adapters and release documentation. The local adapter runs without
production credentials; production-shaped provider gates require the optional
agent, storage, observability, and Postgres dependencies plus real services.

## Start here

1. Read [`AGENTS.md`](AGENTS.md) completely.
2. Read [`docs/README.md`](docs/README.md) for the normative document order.
3. Review [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md).
4. Resolve blocking items in [`docs/governance/assumptions-risks-open-questions.md`](docs/governance/assumptions-risks-open-questions.md).
5. Execute the phases in [`docs/implementation/master-roadmap.md`](docs/implementation/master-roadmap.md).

## Product architecture in one sentence

A persistent central Deep Agent owns the adaptive semantic loop; typed tools, scoped skills, memory, middleware, validation hooks, and specialist subagents form its harness; deterministic services own authorization, canonical persistence, ingestion, rendering, approvals, and external side effects.

AI contribution boundaries are documented in
[`docs/architecture/ai-contribution-boundary.md`](docs/architecture/ai-contribution-boundary.md):
AI implementation lives under `backend/app/ai/` and `frontend/src/ai/`, with
one `backend/app/ai/agent.py` composition root with capability-scoped retrieval,
evaluation, tools, subagents, prompts, middleware configuration, and persistence;
reusable Deep Agents mechanics live in `packages/groundloom-agent-harness/`;
backend access is behind typed adapters in `backend/app/integrations/ai/`;
system prompts are reviewed `.txt` assets rather than inline orchestration
strings.

## Repository state

The backend, frontend, migrations, worker seams, agent harness, retrieval,
review, validation, export, and local operational scripts are implemented.
Remaining unchecked release gates are called out explicitly in
[`docs/validation/release-gates.md`](docs/validation/release-gates.md) and
require external infrastructure or release-owner evidence.

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

For deployment-shaped adapters install the pinned optional groups and configure
their environment variables from `.env.example`:

```powershell
python -m pip install -e ".[dev,documents,postgres,agent,storage,observability]"
```

AI contributors can also install and test the reusable mechanism package alone:

```powershell
python -m pip install -e "packages/groundloom-agent-harness[dev]"
```

The root editable install already includes this package. Deep Agents loads only
published skill versions pinned to the active project through a read-only
`/skills/project/` projection; it never receives the host filesystem.

Set the provider SDK credential required by the selected model (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`) only in the runtime environment. A
missing provider credential produces a retryable dependency error; local mode
continues to use the deterministic adapter.

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The default local identity is `local-user` in `local-workspace`; production mode rejects SQLite, the deterministic model provider, wildcard CORS, and missing auth configuration. Postgres/pgvector and MinIO can be started with `docker compose up -d` for deployment-shaped local testing.

For a production-shaped PostgreSQL deployment, set
`GROUNDLOOM_DATABASE_URL` to the application role,
`GROUNDLOOM_WORKER_DATABASE_URL` to `groundloom_worker`, and
`GROUNDLOOM_MIGRATION_DATABASE_URL` to `groundloom_migrator`. Run migrations
before starting the API or workers; runtime processes do not create tables or
apply schema changes in production.

Validation commands:

```powershell
python -m pytest backend/tests -q
python -m ruff check backend/app backend/tests backend/scripts
python -m mypy backend/app backend/scripts --ignore-missing-imports
python backend/scripts/validate_docs.py
cd frontend; npm run build
cd frontend; npm run test:components
cd ..
python backend/scripts/run_evals.py

# Browser E2E (downloads the pinned local Chromium once)
cd frontend; npx playwright install chromium; npm run test:e2e
cd ..

# Optional bounded worker pass
python backend/scripts/ingestion_worker.py --once
python backend/scripts/export_worker.py
python backend/scripts/retention_worker.py
python backend/scripts/index_worker.py
python backend/scripts/delegated_worker.py
python backend/scripts/agent_worker.py --once
# Requires GROUNDLOOM_OUTBOX_DELIVERY_PROVIDER=webhook and a configured sink.
python backend/scripts/outbox_worker.py --once

# Optional disposable local recovery exercise
cd ..
python backend/scripts/backup_local.py backup --database backend/data/groundloom.db --objects backend/data/objects --destination .local-backup
python backend/scripts/backup_local.py restore --database backend/data/restored.db --objects backend/data/restored-objects --destination .local-backup
```
