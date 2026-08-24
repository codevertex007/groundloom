from datetime import UTC, datetime

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .db import Base, make_engine

MIGRATION_ID = "001_initial_domain_schema"
ADAPTERS_MIGRATION_ID = "002_ingestion_jobs_and_provider_adapters"
RETENTION_EXPORT_MIGRATION_ID = "003_retention_deletion_and_export_leases"


def apply_migrations(database_url: str) -> None:
    from . import models  # noqa: F401

    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(160) PRIMARY KEY, applied_at VARCHAR(64) NOT NULL)"
            )
        )
        migration_ids: list[str] = [
            MIGRATION_ID,
            ADAPTERS_MIGRATION_ID,
            RETENTION_EXPORT_MIGRATION_ID,
        ]
        # create_all creates new tables but does not add columns to a prior
        # release. These additive columns are the only compatibility change in
        # this migration and are safe before the worker is upgraded.
        existing_export_columns = {
            column["name"] for column in inspect(engine).get_columns("export_jobs")
        }
        timestamp_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
        for name, sql_type, default in (
            ("attempts", "INTEGER", "0"),
            ("lease_owner", "VARCHAR(120)", "NULL"),
            ("lease_until", timestamp_type, "NULL"),
        ):
            if name not in existing_export_columns:
                connection.execute(
                    text(f"ALTER TABLE export_jobs ADD COLUMN {name} {sql_type} DEFAULT {default}")
                )
        for migration_id in migration_ids:
            if database_url.startswith("sqlite"):
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (:id, :at)"
                    ),
                    {"id": migration_id, "at": datetime.now(UTC).isoformat()},
                )
            else:
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations (id, applied_at) VALUES (:id, :at) ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": migration_id, "at": datetime.now(UTC).isoformat()},
                )
    engine.dispose(close=True)


def migration_status(db: Session) -> list[str]:
    rows = db.execute(text("SELECT id FROM schema_migrations ORDER BY id")).all()
    return [row[0] for row in rows]
