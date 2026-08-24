"""Bounded specialist/delegated-task worker entrypoint."""

from app.config import get_settings
from app.context import RuntimeContext
from app.db import build_session_factory, init_database
from app.migrations import apply_migrations
from app.services import run_delegated_worker_once


def main() -> None:
    settings = get_settings()
    apply_migrations(settings.database_url)
    engine = init_database(settings.database_url)
    factory = build_session_factory(settings.database_url, engine)
    ctx = RuntimeContext(
        settings.local_user_id,
        settings.local_workspace_id,
        frozenset({"workspace_admin"}),
        "corr-delegated-worker",
    )
    with factory() as db:
        print(run_delegated_worker_once(db, ctx, "delegated-worker", limit=25))
    engine.dispose(close=True)


if __name__ == "__main__":
    main()
