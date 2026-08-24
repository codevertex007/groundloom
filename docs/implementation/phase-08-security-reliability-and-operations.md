# Phase 08 — Security, reliability, and operations hardening

## Checklist

- [ ] `IMPL-08-001` Threat-model review and complete cross-tenant/tool/memory/skill/artifact tests.
- [ ] `IMPL-08-002` Upload/parser/renderer sandboxing, SSRF/network controls, dependency/secret scanning.
- [ ] `IMPL-08-003` Failure injection: API/worker/database/object/provider interruptions at durable boundaries.
- [ ] `IMPL-08-004` Backup/restore and deletion/retention exercises.
- [ ] `IMPL-08-005` Load, queue, context, model-cost, retrieval, and export capacity tests.
- [ ] `IMPL-08-006` Dashboards/alerts/runbooks, SLO/error-budget definitions, on-call-safe diagnostics.
- [ ] `IMPL-08-007` Migration/rollback and old-run compatibility rehearsal.
- [ ] `IMPL-08-008` Privacy/redaction/audit review and incident tabletop.

## Exit gate
No critical/high unresolved security finding; recovery and restore evidence exists; load meets declared envelope; operators can diagnose/recover without raw tenant access.
