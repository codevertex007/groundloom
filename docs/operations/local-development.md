# Local development

Provide one documented command to start Postgres/pgvector, object storage, API, agent worker, ingestion worker, export worker, and frontend with safe local model/provider fakes. Seed synthetic workspace/source/evaluation fixtures; never require production credentials or real tenant data.

Fresh setup, reset of local disposable services, migrations, tests, and UI smoke must be reproducible on supported developer platforms. Production mode rejects local bypasses. Record exact package/runtime versions and troubleshooting for ports, migrations, worker leases, and callback URLs.
