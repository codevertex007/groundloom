# Audit and governance component

Owns append-only audit events, idempotency records, retention/deletion coordination, policy/rubric/prompt/tool version references, and outbox operations. Audit events record actor/service, workspace, action, target, timestamp, result, correlation, and safe change summary without secret/raw sensitive payloads.

Security-sensitive reads, all mutations, approvals, exports/download grants, membership/policy changes, skill/memory writes, retention/deletion, and operator interventions are audited. Audit access is role-scoped and itself audited.

Tests cover tamper resistance through permissions, atomic outbox, replay, redaction, retention exceptions, deletion completeness, clock/correlation, and query isolation.
