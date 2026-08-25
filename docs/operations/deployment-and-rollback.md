# Deployment and rollback

Deploy immutable release SHA: migration compatibility → backend/workers → frontend → smoke. Start the agent, ingestion, index, delegated, export, retention, and configured `outbox_worker.py` processes with the dedicated worker database role. Use health/readiness, queue age, error/latency, agent/provider, retrieval, and outbox dashboards during staged rollout. Outbox delivery is at-least-once; verify the sink deduplicates by event ID before enabling it.

Rollback triggers include tenant/security failure, data corruption/duplication, migration incompatibility, sustained SLO breach, or severe trajectory regression. Roll back code/flags/model profile where compatible, stop risky workers/actions, preserve evidence, and verify reads/writes/replay. Document in-flight run compatibility and kill switches per release.
