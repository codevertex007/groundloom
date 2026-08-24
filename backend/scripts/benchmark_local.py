"""Measure the disposable local retrieval envelope.

This is a smoke/load check, not production capacity evidence. It creates only
synthetic data in a temporary directory and emits p50/p95 latency JSON.
"""

import argparse
import base64
import json
import statistics
import tempfile
import time
from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=50)
    args = parser.parse_args()
    count = max(1, min(args.requests, 500))
    with tempfile.TemporaryDirectory(prefix="groundloom-benchmark-") as directory:
        root = Path(directory)
        settings = Settings(
            database_url="sqlite://",
            object_store_path=root / "objects",
        )
        app = create_app(settings)
        with TestClient(app) as api:
            upload = api.post(
                "/v1/sources/uploads",
                json={
                    "name": "Synthetic benchmark source",
                    "filename": "benchmark.txt",
                    "content_base64": base64.b64encode(
                        b"retrieval evidence " * 500
                    ).decode(),
                },
            )
            upload.raise_for_status()
            source_version_id = upload.json()["current_version_id"]
            project = api.post(
                "/v1/projects",
                json={
                    "name": "Synthetic benchmark project",
                    "brief": "Measure local retrieval.",
                    "source_version_ids": [source_version_id],
                },
            )
            project.raise_for_status()
            project_id = project.json()["id"]
            timings = []
            for _ in range(count):
                started = time.perf_counter()
                response = api.get(f"/v1/projects/{project_id}/sources/search?q=evidence")
                response.raise_for_status()
                timings.append((time.perf_counter() - started) * 1000)
        app.state.db_engine.dispose(close=True)
        ordered = sorted(timings)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        print(
            json.dumps(
                {
                    "requests": count,
                    "p50_ms": round(statistics.median(timings), 3),
                    "p95_ms": round(p95, 3),
                    "max_ms": round(max(timings), 3),
                    "adapter": "sqlite+filesystem",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
