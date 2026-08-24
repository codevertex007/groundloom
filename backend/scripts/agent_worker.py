"""Local worker entrypoint; interactive runs are durable and resumable."""

from app.config import get_settings
from app.db import build_session_factory, init_database
from app.migrations import apply_migrations

if __name__ == "__main__":
    settings = get_settings()
    apply_migrations(settings.database_url)
    init_database(settings.database_url)
    build_session_factory(settings.database_url)
    print("Groundloom agent worker is ready; API commands enqueue durable runs.")

