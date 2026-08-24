# Product requirements

**Status:** Accepted baseline  
**Product:** Groundloom — source-grounded knowledge production studio

## Problem

Teams need to turn large, changing source collections into structured, reviewable, cited deliverables. Existing chat tools lose project state, hide provenance, mix drafting with commitment, and provide weak control over reusable organizational instructions.

## Product outcome

Groundloom provides one persistent AI collaborator per project. The collaborator uses selected sources and versioned skills, exposes its plan and progress, produces typed/cited drafts, accepts targeted feedback, and proposes reviewable changes. Users retain deterministic control over canonical content and export.

## Personas

- **Author:** creates projects, selects sources/skills, directs generation, reviews edits, exports.
- **Reviewer:** inspects citations, quality results, and proposals; accepts/rejects when permitted.
- **Workspace administrator:** manages membership, organization/workspace skills, defaults, retention, and policy.
- **Operator:** deploys, monitors, restores, and troubleshoots the system without accessing tenant content unnecessarily.

## Functional requirements

- **FR-PROJECT-001:** A user MUST create a project with type, brief, source selection, active skills, and defaults.
- **FR-PROJECT-002:** The project MUST retain one persistent primary-agent thread across setup, generation, editing, review, and export discussion.
- **FR-PROJECT-003:** Users MUST see durable lifecycle and actionable progress after reload/reconnect.
- **FR-SOURCE-001:** Users MUST upload and version supported source files without overwriting historical versions.
- **FR-SOURCE-002:** The system MUST expose immutable evidence passages with page/block lineage.
- **FR-SOURCE-003:** Retrieval MUST be limited to authorized, selected source versions.
- **FR-SKILL-001:** Skills MUST be versioned packages with starter, organization, workspace, and project-active scopes.
- **FR-SKILL-002:** AI-created skills MUST remain drafts until validation and authorized publication.
- **FR-AGENT-001:** The primary agent MUST choose an adaptive trajectory rather than follow a mandatory semantic phase graph.
- **FR-AGENT-002:** The primary agent MUST support planning/todos, direct tool use, specialist delegation, validation, and targeted repair.
- **FR-CONTENT-001:** Generated deliverables MUST use typed, ordered content blocks.
- **FR-CONTENT-002:** Factual, numeric, and safety-relevant claims MUST be traceable to source passages or explicitly marked unsupported.
- **FR-CONTENT-003:** Agent edits MUST be stored as proposals against an immutable base content version.
- **FR-CONTENT-004:** Accept/Reject MUST be deterministic, auditable commands; Reject MUST leave canonical content unchanged.
- **FR-CONTENT-005:** Conflicting concurrent edits MUST not silently overwrite each other.
- **FR-QUALITY-001:** Users MUST see deterministic and semantic validation results with affected content and evidence.
- **FR-EXPORT-001:** Users MUST preview/export an immutable content version through deterministic workers.
- **FR-AUDIT-001:** The system MUST explain the run inputs and versions that produced a content version or artifact.

## Explicit non-goals for v1

- General web crawling; real-time CRDT collaboration; arbitrary agent shell access; autonomous publication outside Groundloom; training models; replacing professional/legal/safety review; generic workflow automation unrelated to knowledge production.

## Success signals

- Users reach a reviewable cited outline/draft without losing project context.
- High proposal acceptance with low post-accept correction rate.
- Citation navigation succeeds and historical runs remain reproducible.
- Interrupted runs resume without duplicate effects.
- A solo operator can deploy, observe, evaluate, and recover the product.
