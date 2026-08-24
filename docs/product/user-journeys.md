# User journeys

## J1 — Create and begin a project

1. Author selects project type, sources, brief, and active skill versions.
2. API validates authorization/configuration and creates the project plus primary thread.
3. Primary agent hydrates a compact project snapshot and decides whether clarification is material.
4. Agent may ask, inspect sources, build todos, or propose an outline.
5. User can leave and resume from durable thread/run state.

Acceptance: `FR-PROJECT-001..003`, `FR-AGENT-001`, `TEST-E2E-001`.

## J2 — Ingest and use a source

Upload is scanned, parsed/OCRed, normalized, chunked, embedded, indexed, and quality checked. Failures expose a stage and retry policy. A running project remains pinned to selected versions; a new run may opt into a newer version. Citation navigation reaches immutable passage lineage.

Acceptance: `FR-SOURCE-001..003`, `TEST-E2E-004`, `TEST-SEC-006`.

## J3 — Generate an outline and modules

The primary agent plans when useful, researches evidence, directly handles small scope or delegates independent modules, reconciles results, validates, repairs only failed scope, and creates a reviewable proposal. Plan approval is an interrupt in the same thread, not a handoff to another workflow.

Acceptance: `FR-AGENT-001..002`, `FR-CONTENT-001..002`, `TEST-TRAJ-001..006`.

## J4 — Request and review an edit

User asks for a change or selects blocks. The primary agent reads the current version, retrieves bounded evidence, proposes typed patch operations, and presents a diff. Reject changes no canonical state. Accept checks the base version and commits exactly one new version or returns conflict.

Acceptance: `FR-CONTENT-003..005`, `TEST-E2E-002`, `TEST-CONTRACT-042`.

## J5 — Create a reusable skill

User asks the skill-author agent to draft a package. The system validates frontmatter, references, trigger specificity, package size, tool names, policy conflicts, and examples. Publication requires authorization and approval at organization scope. Project runs pin selected published versions.

Acceptance: `FR-SKILL-001..002`, `TEST-E2E-005`.

## J6 — Validate and export

Deterministic checks and bounded semantic review produce evidence-linked results. User chooses an immutable content/template version and starts export. A deterministic worker renders, stores, and reports one artifact despite retries. Download uses short-lived authorization.

Acceptance: `FR-QUALITY-001`, `FR-EXPORT-001`, `TEST-E2E-006`.
