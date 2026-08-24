# Documentation contract

## Normative language

`MUST`/`MUST NOT` are mandatory. `SHOULD` describes the expected default; deviations require written rationale. `MAY` is optional. Statements without one of these terms are explanatory unless attached to an acceptance criterion.

## Document header

New normative documents must state status (`Draft`, `Accepted`, `Superseded`), owner, last reviewed date, and affected requirement namespaces. ADRs use their own status field.

## Requirement quality

Every requirement must be atomic, testable, uniquely identified, and written at the boundary observable by its consumer. Do not encode implementation detail in an `FR` unless the implementation is itself required. Architecture invariants belong under `ARCH`, data rules under `DATA`, and security rules under `SEC`.

## Change rules

- Preserve IDs once referenced. Mark removed requirements `Retired`; never reuse their IDs.
- A semantic change requires updating acceptance criteria and tests.
- A contract-breaking change requires a versioning decision and migration/compatibility plan.
- An architecture decision requires an ADR or an amendment to the ADR that owns it.
- Examples must be valid against current schemas.
- Checklist completion requires evidence: test name, trace, migration result, screenshot, or reviewed manual record.

## Review gate

A change is documentation-complete when links resolve, IDs are unique, affected matrices are updated, examples validate, no unresolved contradiction exists, and the implementation handoff lists all changed normative documents.
