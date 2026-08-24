from app.config import get_settings
from app.migrations import apply_migrations

if __name__ == "__main__":
    settings = get_settings()
    apply_migrations(settings.database_url)
    print("Applied Groundloom migrations")

