"""Postgres-leased ingestion worker.

Use ``--once`` for a bounded local run. A supervisor should invoke the same
entrypoint repeatedly in deployment; leases make worker death recoverable.
"""

import argparse

from app.config import get_settings
from app.context import RuntimeContext
from app.db import prepare_worker_database
from app.services import run_ingestion_worker_once

if __name__ == "__main__":
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default="ingestion-local")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    _worker_database_url, engine, factory = prepare_worker_database(settings)
    try:
        if args.once:
            with factory() as db:
                ctx = RuntimeContext(
                    settings.local_user_id,
                    settings.local_workspace_id,
                    frozenset({"workspace_admin"}),
                    "corr_worker",
                )
                print(run_ingestion_worker_once(db, ctx, settings, args.worker_id, limit=args.limit))
        else:
            print("Groundloom ingestion worker is ready; run with --once under a supervisor.")
    finally:
        engine.dispose(close=True)
