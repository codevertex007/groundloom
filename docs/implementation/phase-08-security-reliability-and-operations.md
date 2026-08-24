# Phase 08 — Security, reliability, and operations hardening

## Checklist

- [x] `IMPL-08-001` Threat-model boundary, signed runtime identity, cross-tenant/tool/memory/skill/artifact tests; live identity/RLS review remains deployment evidence.
- [x] `IMPL-08-002` Upload/parser safety limits, MIME-spoof rejection, source-instruction signals, path-safe artifacts, and dependency audit; sandbox/container review remains deployment evidence.
- [x] `IMPL-08-003` Local failure/replay tests for leased ingestion, object-store paths, provider configuration, and bounded retries; live database/provider interruption injection remains open.
- [x] `IMPL-08-004` Local checksum-backed backup/restore exercise; production Postgres/object-store restore remains open.
- [x] `IMPL-08-005` Synthetic local retrieval benchmark with p50/p95 output; production capacity/cost envelope remains open.
- [x] `IMPL-08-006` Local dashboard dimensions, alert thresholds, runbooks, SLO/error-budget starting thresholds, and redacted diagnostics are documented; production monitoring wiring remains open.
- [x] `IMPL-08-007` Fresh-install migration sequence verification and compatibility boundaries are automated; previous-release/rollback rehearsal remains deployment evidence.
- [x] `IMPL-08-008` Local privacy/redaction/audit review and incident response controls are documented/tested; production tabletop remains open.

## Exit gate
No critical/high unresolved security finding; recovery and restore evidence exists; load meets declared envelope; operators can diagnose/recover without raw tenant access.
