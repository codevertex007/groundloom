# Configuration contract

Configuration groups: application/environment, database/checkpointer, object storage, worker/lease, model profiles, embedding/reranking, Langfuse/telemetry, upload/parser limits, agent/context/budget limits, security/retention, and feature flags.

Every setting has type, default where safe, required environments, secret classification, validation, and reload policy. Production refuses startup on missing secrets, invalid public URLs, unsafe CORS, disabled auth, absent encryption configuration, or in-memory checkpoint/storage configuration.

Feature flags do not bypass authorization/invariants and have owner, purpose, default, creation/removal date, metrics, and rollback behavior. Log a redacted effective configuration fingerprint, not secret values.

The local defaults are explicit: SQLite domain state, a filesystem object store,
local deterministic agent runtime, local JSON checkpoints, and local redacted
telemetry. Deployment settings select `checkpoint_backend=postgres`,
`object_store_backend=s3`, a configured model provider, and
`telemetry_provider=langfuse`; production startup rejects any local substitute.
Optional dependency groups are `agent`, `storage`, and `observability`.
Provider calls use at most `agent_max_attempts` (default 3) with bounded
exponential backoff; cancellation is checked before each retry.
