"""Verify fresh-install migration ordering for the local release gate."""

import tempfile
from pathlib import Path

from app.db import build_session_factory
from app.migrations import apply_migrations, migration_status

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="groundloom-migrations-") as directory:
        database = Path(directory) / "fresh.db"
        url = f"sqlite:///{database}"
        apply_migrations(url)
        factory = build_session_factory(url)
        with factory() as db:
            applied = migration_status(db)
        factory.kw["bind"].dispose(close=True)
        expected = [
            "001_initial_domain_schema",
            "002_ingestion_jobs_and_provider_adapters",
            "003_retention_deletion_and_export_leases",
            "004_index_rebuild_jobs",
        ]
        if applied != expected:
            raise SystemExit(f"Unexpected migration sequence: {applied}")
        print({"status": "ok", "migrations": applied})
