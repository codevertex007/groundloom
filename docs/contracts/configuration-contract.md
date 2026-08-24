# Configuration contract

Configuration groups: application/environment, database/checkpointer, object storage, worker/lease, model profiles, embedding/reranking, Langfuse/telemetry, upload/parser limits, agent/context/budget limits, security/retention, and feature flags.

Every setting has type, default where safe, required environments, secret classification, validation, and reload policy. Production refuses startup on missing secrets, invalid public URLs, unsafe CORS, disabled auth, absent encryption configuration, or in-memory checkpoint/storage configuration.

Feature flags do not bypass authorization/invariants and have owner, purpose, default, creation/removal date, metrics, and rollback behavior. Log a redacted effective configuration fingerprint, not secret values.
