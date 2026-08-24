# Deployment and rollback

Deploy immutable release SHA: migration compatibility → backend/workers → frontend → smoke. Use health/readiness, queue age, error/latency, agent/provider, retrieval, and outbox dashboards during staged rollout.

Rollback triggers include tenant/security failure, data corruption/duplication, migration incompatibility, sustained SLO breach, or severe trajectory regression. Roll back code/flags/model profile where compatible, stop risky workers/actions, preserve evidence, and verify reads/writes/replay. Document in-flight run compatibility and kill switches per release.
