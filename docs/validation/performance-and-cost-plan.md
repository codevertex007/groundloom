# Performance and cost plan

Measure API p50/p95/p99, first durable agent activity, retrieval latency/quality, queue wait, model/tool/subagent spans, context size/compaction, tokens/cost per accepted module, ingestion throughput, render time, SSE replay, database/object utilization, and cancellation latency.

Scenarios follow the v1 scale envelope with burst and degraded-provider variants. Establish budgets by project/module/source size. Fail tests on unbounded query/result/context/concurrency growth, not only latency. Compare model/retrieval changes on quality and cost together; cheaper but materially worse trajectories do not pass.
## Local evidence

Run the synthetic retrieval envelope without customer data:

```powershell
$env:PYTHONPATH = "backend"
python backend/scripts/benchmark_local.py --requests 50
```

The script reports p50/p95/max latency and identifies the SQLite/filesystem
adapter. It is deliberately not a production SLO claim; the release gate
requires the same scenarios against Postgres/pgvector, object storage, workers,
and the configured model profile with queue, context, and cost measurements.
