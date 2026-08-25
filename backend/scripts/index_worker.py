"""Deterministic derived lexical-index rebuild worker."""

from app.config import get_settings
from app.context import RuntimeContext
from app.db import prepare_worker_database
from app.services import run_index_rebuild_worker_once


def main() -> None:
    settings = get_settings()
    _worker_database_url, engine, factory = prepare_worker_database(settings)
    ctx = RuntimeContext(
        settings.local_user_id,
        settings.local_workspace_id,
        frozenset({"workspace_admin"}),
        "corr-index-worker",
    )
    with factory() as db:
        print(run_index_rebuild_worker_once(db, ctx, "index-worker", limit=25, settings=settings))
    engine.dispose(close=True)


if __name__ == "__main__":
    main()
