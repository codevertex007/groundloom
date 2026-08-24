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
development adapter renders exports inline by default; set
GROUNDLOOM_EXPORT_INLINE_LOCAL=false to exercise the durable export worker.

Fresh setup, reset of local disposable services, migrations, tests, and UI smoke must be reproducible on supported developer platforms. Production mode rejects local bypasses. Record exact package/runtime versions and troubleshooting for ports, migrations, worker leases, and callback URLs.
