from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, make_engine

MIGRATION_ID = "001_initial_domain_schema"
ADAPTERS_MIGRATION_ID = "002_ingestion_jobs_and_provider_adapters"


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
        migration_ids = (MIGRATION_ID, ADAPTERS_MIGRATION_ID)
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


def migration_status(db: Session) -> list[str]:
    rows = db.execute(text("SELECT id FROM schema_migrations ORDER BY id")).all()
    return [row[0] for row in rows]
