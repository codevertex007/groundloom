"""Durable primary-agent worker entrypoint."""

import argparse
import time
from uuid import uuid4

from app.config import get_settings
from app.db import build_session_factory, init_database, make_engine
from app.migrations import apply_migrations
from app.services import run_agent_worker_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued Groundloom agent runs")
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument("--limit", type=int, default=10, help="Maximum runs per batch")
    args = parser.parse_args()
    settings = get_settings()
    # Local/test workers share the convenience database bootstrap. Production
    # migrations run under an administrative deployment path; the worker uses
    # a dedicated groundloom_worker role for forced-RLS queue access.
    if settings.env != "production":
        apply_migrations(settings.database_url)
        init_database(settings.database_url)
    worker_database_url = settings.worker_database_url or settings.database_url
    engine = make_engine(worker_database_url)
    factory = build_session_factory(worker_database_url, engine)
    worker_id = f"agent-{uuid4().hex[:12]}"
    try:
        while True:
            with factory() as db:
                result = run_agent_worker_once(db, settings, worker_id, limit=args.limit)
            print(result, flush=True)
            if args.once:
                return
            time.sleep(max(0.1, min(args.interval, 60.0)))
    finally:
        engine.dispose(close=True)


if __name__ == "__main__":
    main()
