# Deployment architecture

Environments: local, test, staging, production. Configuration is environment supplied and validated at startup; secrets use the deployment secret manager. Images/build artifacts are immutable and tagged by release SHA.

Deploy order: compatible database migration → backend/workers → frontend; destructive schema cleanup occurs only after compatibility windows. Agent dependency/prompt/tool changes are versioned so in-flight runs can resume against compatible definitions or fail with a clear migration policy.

Health endpoints distinguish liveness, readiness, database/checkpointer access, worker heartbeat, queue age, object storage, and optional provider degradation. Model/provider outage should preserve read/review/export of existing content where possible.

Rollback never assumes database rollback is safe. Use expand/migrate/contract, feature flags for risky behavior, and explicit run-version compatibility. See operations runbooks for deploy, migration, backup, and incidents.
