# Groundloom master implementation checklist

This is the portfolio view. Detailed, authoritative tasks and exit evidence live in each phase document.

- [x] **Phase 00:** repository, contracts, local infrastructure, CI, documentation validation — evidence in `phase-00-repository-and-contracts.md`
- [x] **Phase 01:** identity, tenant-safe domain model, persistence, audit, outbox, base APIs (local adapter evidence; production Postgres/RLS gate remains)
- [x] **Phase 02:** immutable sources, deterministic ingestion, retrieval, evidence lineage (local adapter evidence; durable worker/OCR/load gate remains)
- [x] **Phase 03:** persistent primary Deep Agent, context, read tools, planning, streaming, recovery (local deterministic runtime evidence; verified provider adapter gate remains)
- [x] **Phase 04:** skills, memory, middleware, specialist subagents, durable delegation (local bounded delegation evidence)
- [x] **Phase 05:** typed outline/content, citations, proposals, diffs, Accept/Reject, concurrency
- [x] **Phase 06:** validation, semantic evaluation, targeted repair, export/preview (deterministic local evaluation; semantic provider gate remains)
- [x] **Phase 07:** complete reference UI, accessibility, reconnect/error/permission behavior (10-test browser suite, component tests, axe scan, and pinned visual baselines)
- [ ] **Phase 08:** security, resilience, backup/restore, operations, capacity/cost hardening
- [ ] **Phase 09:** traceability closure, staging/rollback, pilot, production release evidence

## Rule for checking a box

Do not check a phase or task merely because code was merged. The phase document's exit gate must have links to passing test/evaluation runs, migration evidence, required operational exercise, and updated documentation/traceability. Any waiver is recorded in `validation/release-gates.md` with owner and expiry.
