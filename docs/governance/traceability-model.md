# Traceability model

Groundloom uses bidirectional traceability so Codex can determine what to implement and reviewers can determine why code exists.

## Chain

```text
Product requirement
→ architecture/security invariant
→ ADR
→ API/tool/event/data contract
→ component responsibility
→ implementation checklist item
→ automated test/evaluation
→ release evidence
```

Example:

```text
FR-CONTENT-008 proposed edits are non-canonical
→ ARCH-STATE-004 proposal/commit separation
→ ADR-006
→ TOOL-CONTENT-003 propose_block_patch
→ components/patches-and-review.md
→ IMPL-05-017
→ TEST-CONTRACT-042 and TEST-E2E-011
```

## Matrix rules

- Every active `FR`, `NFR`, `SEC`, `API`, `TOOL`, and `EVT` ID appears in `validation/requirements-test-matrix.md`.
- Every code change names the IDs it satisfies or modifies.
- Tests should include requirement IDs in docstrings/metadata where the test framework permits.
- Orphan code is challenged during review; orphan requirements block release.
- Manual-only verification requires owner, procedure, evidence location, and expiration/review date.

## Drift handling

If implementation reveals the specification is wrong, Codex must not silently follow the code. It records the discrepancy, proposes the normative update and any ADR change, then modifies code, tests, and docs together after the decision is accepted.
