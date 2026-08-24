# Domain architecture

## Aggregates

- Workspace/membership controls tenant boundary.
- Project owns configuration-version selection and current content/outline pointers.
- Source owns immutable source versions and ingestion state.
- Skill owns immutable skill versions and publication state.
- Content owns immutable versions, blocks, citations, proposals, and decisions.
- Run owns public activity/events/approvals and references execution threads.
- Export owns render request, template version, job, artifact, and expiry.

## Command/query rules

Commands enforce authorization, invariants, idempotency, optimistic concurrency, and emit outbox events in the same transaction. Queries return bounded product DTOs and never leak checkpoint or provider schemas. Cross-aggregate workflows coordinate through services/events rather than direct table mutation.

## Invariants

- Every tenant record has `workspace_id`.
- Immutable versions are never edited in place.
- Current pointers change only through domain commands.
- A proposal targets exactly one base content version.
- Citation lineage targets exactly one source version.
- A run records pinned inputs before output is committed.
- Public status history is append-only.
