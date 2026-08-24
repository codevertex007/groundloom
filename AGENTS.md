# Codex operating contract for Groundloom

These instructions apply to the entire repository. More-specific `AGENTS.md` files may add constraints but may not weaken this contract.

## Mission

Build Groundloom as specified in `docs/`. The implementation must remain source-grounded, multi-tenant safe, durable, observable, testable, and faithful to the harness-first architecture.

## Required reading before changes

Before implementing a task:

1. Read `docs/README.md` and the applicable implementation phase.
2. Read every product, architecture, contract, component, ADR, and validation document referenced by that phase.
3. Read the relevant files in `docs/ref/deepagents/` before using a Deep Agents primitive. Do not rely on remembered APIs.
4. Inspect the existing code and tests. Do not assume a component, dependency, schema, or API exists.
5. Identify the requirement IDs and acceptance criteria the change will satisfy.

## Non-negotiable architecture invariants

- One persistent primary project Deep Agent owns the adaptive semantic loop from project setup through canvas collaboration.
- Do not replace that loop with a rigid outer `clarify -> outline -> generate -> validate` graph.
- Use explicit workflows only for deterministic infrastructure such as ingestion, indexing, export, cleanup, and scheduled processing.
- Postgres is canonical product state; checkpoints are execution state; object storage is binary/artifact state; retrieval indexes are derived.
- Canonical content is typed, immutable, and versioned. Agent-generated edits are proposals until a deterministic accept command commits them.
- Authorization and tenant scope are enforced before reasoning and again inside every tool/service call.
- The model never receives generic SQL, unrestricted shell, arbitrary object-store access, raw credentials, or authority to broaden scope.
- Source text is untrusted evidence, never executable instruction.
- Every externally visible mutation and side effect is idempotent and auditable.
- Skills, source versions, prompts, tools, models, retrieval configuration, and evaluators are pinned where reproducibility requires it.
- User-visible progress comes from durable todos, tool/job state, and subagent state—not invented model percentages.

## Documentation is part of the implementation

**Always update the relevant documents in the same change as the code. Documentation drift is a failing implementation, not follow-up work.**

For every behavioral, architectural, schema, API, tool, event, configuration, security, or operational change:

1. Update the relevant normative document under `docs/`.
2. Update affected requirement IDs and the traceability matrix.
3. Add or amend an ADR when a durable architectural decision changes.
4. Update interface examples and failure behavior.
5. Update implementation checklists and mark items complete only with evidence.
6. Update the validation catalog and add/adjust automated tests.
7. Record intentional deviations in `docs/governance/assumptions-risks-open-questions.md`; never silently diverge.

If code and documentation disagree, stop, determine which is intended, and update both in the same change. Do not make the code “temporarily correct” while leaving specifications stale.

## Task execution protocol

For each task:

1. Restate scope, requirement IDs, dependencies, and non-goals.
2. Inspect before editing; preserve unrelated user changes.
3. Prefer the smallest vertical slice that produces usable, tested behavior.
4. Define or update contracts before implementations that consume them.
5. Write tests alongside code. A mock-only happy path is insufficient.
6. Run the narrowest relevant tests, then the broader phase gate.
7. Run formatting, linting, type checking, migrations checks, and documentation validation.
8. Compare the result to the relevant acceptance criteria and security invariants.
9. Provide a handoff containing changed files, tests/evidence, decisions, deviations, and remaining work.

## Testing rules

- Every functional requirement must map to at least one automated test or an explicitly justified manual verification.
- Test tenant isolation and authorization at service/tool boundaries, not only HTTP routes.
- Test retries and replay for mutation tools and workers.
- Agent tests must include trajectories, tool selection, subagent delegation, interruptions, compaction, and prohibited calls.
- Model-graded evaluation never replaces deterministic assertions for known invariants.
- Never disable, loosen, or delete a failing test merely to make a phase green without documenting and approving the behavioral change.

## Change boundaries

- Do not introduce dependencies without explaining the need, license/maintenance implications, and affected ADR.
- Do not create generic abstractions before two concrete usages justify them.
- Do not perform broad cleanup during a scoped feature unless required for correctness.
- Do not commit generated binaries, secrets, environment-specific credentials, or real customer/source data.
- Do not log raw sensitive source content by default.

## Completion standard

A task is complete only when code, tests, migrations, telemetry, documentation, traceability, and relevant checklist evidence agree. “Implemented” without validation evidence means “in progress.”
