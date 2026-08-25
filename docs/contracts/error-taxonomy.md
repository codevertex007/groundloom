# Error taxonomy

Error envelope: stable `code`, safe `message`, correlation ID, retryable flag, optional field violations/current version/action hint. Internal cause/stack is logged with redaction, not returned.

Classes: `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`, `INVALID_INPUT`, `INVALID_STATE`, `VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `APPROVAL_REQUIRED/EXPIRED`, `BUDGET_EXCEEDED`, `SOURCE_NOT_READY`, `SOURCE_QUARANTINED`, `NO_EVIDENCE`, `CONTRADICTORY_EVIDENCE`, `MODEL_OUTPUT_INVALID`, `PROVIDER_TRANSIENT`, `DEPENDENCY_UNAVAILABLE`, `JOB_FAILED`, `CANCELLED`, `INTERNAL_ERROR`.

Retry policy belongs to the class plus operation: transient failures use bounded backoff; validation requests revised input; conflicts require refresh/rebase; permission failures stop; cancellation stays terminal unless a new run is created. User messages must be actionable without leaking inaccessible object existence or secrets.
