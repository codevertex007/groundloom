import argparse

from app.ai.persistence.checkpoints import setup_postgres_checkpoint_schema
from app.config import Settings
from app.migrations import apply_migrations

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Groundloom schema migrations")
    parser.add_argument(
        "--database-url",
        help="Override the migration database URL (use only for an approved deployment target)",
    )
    args = parser.parse_args()
    settings = Settings()
    if args.database_url:
        settings.migration_database_url = args.database_url
    settings.validate_runtime()
    database_url = settings.migration_database_url or settings.database_url
    apply_migrations(database_url)
    if settings.checkpoint_backend == "postgres" and database_url.startswith("postgres"):
        setup_postgres_checkpoint_schema(database_url)
    print("Applied Groundloom migrations")
