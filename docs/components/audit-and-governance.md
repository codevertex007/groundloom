# Audit and governance component

Owns append-only audit events, idempotency records, retention/deletion coordination, policy/rubric/prompt/tool version references, and outbox operations. Audit events record actor/service, workspace, action, target, timestamp, result, correlation, and safe change summary without secret/raw sensitive payloads.

Security-sensitive reads, all mutations, approvals, exports/download grants, membership/policy changes, skill/memory writes, retention/deletion, and operator interventions are audited. Audit access is role-scoped and itself audited. Workspace and organization administrators can query a bounded, cursor-paginated safe projection through `GET /v1/audit-events`; authors and reviewers receive a typed permission error without an existence leak. The read event is written after the requested page is materialized so it cannot alter or duplicate the page being returned.

Tests cover tamper resistance through permissions, atomic outbox, replay, redaction, bounded audit pagination/cursor rejection, retention exceptions, deletion completeness, clock/correlation, and query isolation.
