"""Ingestion worker health entrypoint.

The local adapter finalizes small uploads synchronously. This process exists as
the deployment seam for leased ingestion jobs and can be scaled independently.
"""

from app.config import get_settings
from app.migrations import apply_migrations

if __name__ == "__main__":
    settings = get_settings()
    apply_migrations(settings.database_url)
    print("Groundloom ingestion worker is ready.")

