"""Durable transactional-outbox publisher.

The worker never treats a disabled local sink as successful delivery. Configure
the narrow webhook adapter in staging/production; downstream consumers must
deduplicate by the stable outbox event ID.
"""

import argparse
import time
from uuid import uuid4

from app.application.operations import touch_worker_heartbeat
from app.config import get_settings
from app.db import prepare_worker_database, set_worker_context
from app.outbox import build_delivery, publish_pending


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish pending Groundloom outbox events")
    parser.add_argument("--once", action="store_true", help="Publish one bounded batch and exit")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument("--limit", type=int, default=100, help="Maximum events per batch")
    args = parser.parse_args()
    settings = get_settings()
    delivery = build_delivery(settings)
    _worker_database_url, engine, factory = prepare_worker_database(settings)
    worker_id = f"outbox-{uuid4().hex[:12]}"
    try:
        while True:
            with factory() as db:
                set_worker_context(db)
                touch_worker_heartbeat(
                    db, worker_id, "outbox", status="healthy", details={"limit": args.limit}
                )
                db.commit()
                published = publish_pending(db, delivery, limit=max(1, min(args.limit, 500)))
                touch_worker_heartbeat(
                    db,
                    worker_id,
                    "outbox",
                    status="healthy",
                    details={"published": published},
                )
                db.commit()
            print({"published": published}, flush=True)
            if args.once:
                return
            time.sleep(max(0.1, min(args.interval, 60.0)))
    finally:
        engine.dispose(close=True)


if __name__ == "__main__":
    main()
