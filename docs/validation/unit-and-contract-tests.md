# Unit and contract test catalog

Unit suites: domain state transitions/invariants; role/policy resolution; settings precedence; block/patch/citation schemas; version pinning; idempotency; error classification; skill parsing/resolution; evidence serialization; middleware ordering/visibility; context budgeting; progress computation.

Contract suites: every REST operation/error/idempotency/version case; every tool input/output/auth/bound; SSE/domain event envelopes and additive compatibility; subagent task/result schemas; provider/parser/storage adapters with fakes.

Use property-based tests for typed patch sequences, state transitions, path normalization, idempotency combinations, and event ordering where useful. Snapshot tests require schema-aware review and must not normalize away meaningful changes.
