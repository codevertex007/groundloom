# Phase 09 — Production readiness

## Checklist

- [ ] `IMPL-09-001` Close/accept all release-blocking requirements, risks, and open decisions; the external release-evidence register is complete, but live acceptance remains required.
- [ ] `IMPL-09-002` Complete bidirectional requirements-test-code evidence matrix.
- [ ] `IMPL-09-003` Run full CI, eval, security, accessibility, load, migration, backup/restore gates on release candidate.
- [ ] `IMPL-09-004` Validate production configuration/secrets/domains/storage/identity/telemetry/retention.
- [ ] `IMPL-09-005` Stage deployment, smoke, soak, rollback rehearsal, provider-degradation exercise.
- [ ] `IMPL-09-006` Pilot rollout with feature flags, budgets, feedback, support/incident ownership.
- [ ] `IMPL-09-007` Review launch metrics and expand gradually; preserve rollback/kill switches.
- [x] `IMPL-09-008` Publish local release evidence, known limitations, and operations handoff in `validation/release-candidate-evidence.md`; production sign-off remains external.

## Exit gate
Release owner signs `validation/release-gates.md`; production smoke and rollback pass; no undocumented implementation/spec drift exists.
