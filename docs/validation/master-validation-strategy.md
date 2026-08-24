# Master validation strategy

Validation layers:

1. Static: format, lint, type, dependency, docs links/IDs, architecture imports.
2. Unit: domain invariants, schemas, policies, helpers, middleware units.
3. Contract: REST/OpenAPI, tools, events, subagents, adapters.
4. Integration: real Postgres/checkpointer/pgvector/object storage/workers/outbox.
5. Retrieval/component evals: evidence lineage and structured outputs.
6. Agent trajectory evals: decisions/actions/prohibitions under pinned models.
7. E2E: browser/API/worker/model-fake and selected live-model staging journeys.
8. Security/reliability/performance/accessibility.
9. Production smoke/soak and online quality feedback.

Deterministic invariants use deterministic assertions. Model graders supplement but do not replace them. Flaky tests are quarantined only with owner, issue, bounded deadline, and non-blocking rationale; security/tenant/idempotency gates cannot be quarantined for release.
