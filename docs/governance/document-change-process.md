# Document change process

1. Identify affected IDs, contracts, components, ADRs, tests, and phase checklist items.
2. Classify the change as clarification, compatible behavior, breaking contract, architecture decision, or retirement.
3. Update the highest-authority document first.
4. Add/amend an ADR for durable structural decisions.
5. Update downstream contracts, examples, checklists, and traceability.
6. Implement and test the change.
7. Validate links, schemas, tests, and release gates.
8. Record deviations and unresolved consequences.

Breaking changes must include compatibility behavior, migration steps, rollback, observability, and a removal date for temporary compatibility paths. Emergency production changes may precede full prose only when necessary to contain an incident; the incident follow-up must reconcile documents and tests before normal feature work resumes.
