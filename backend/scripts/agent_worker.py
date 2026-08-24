"""Durable primary-agent worker entrypoint."""

import argparse
import time
from uuid import uuid4

from app.config import get_settings
from app.db import prepare_worker_database
from app.services import run_agent_worker_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued Groundloom agent runs")
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument("--limit", type=int, default=10, help="Maximum runs per batch")
    args = parser.parse_args()
    settings = get_settings()
    _worker_database_url, engine, factory = prepare_worker_database(settings)
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
