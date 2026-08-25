# ADR-033: Reusable Deep Agents harness and application composition boundary

- Status: Accepted
- Date: 2026-08-25
- Deciders: Groundloom engineering

## Context

ADR-032 separated AI files from the backend, but the first implementation still
mixed reusable Deep Agents mechanics with Groundloom persistence and put
retrieval provider code in a generic provider directory. It also filtered
Deep Agents' `read_file` and `ls` tools, preventing selected `SKILL.md` packages
from being discovered at runtime. Tool closures imported the monolithic product
service module directly, making independent AI and backend contribution hard.

## Decision

Maintain a small installable `groundloom-agent-harness` package containing only
framework-level contracts and mechanisms: atomic budgets, cancellation, safe
event projection, tool policy middleware, stream normalization, and a bounded
read-only skill backend. The package does not wrap `create_deep_agent` and does
not import Groundloom application code.

Keep one Groundloom composition root at `backend/app/ai/agent.py`. It is the only
module that calls `create_deep_agent` and composes the model, external prompt and
subagent-description assets, typed tools, middleware, selected skills, subagents, runtime context,
checkpointer, and stream projection.

Organize application AI code by capability. Retrieval owns its service,
contracts, and embedding/reranking providers; `tools/retrieval.py` exposes that
capability to the model. Evaluation, persistence, prompts, subagents, and shared
AI HTTP utilities have explicit directories. Model-facing tools depend only on
`AgentServicePort`. `backend/app/integrations/ai/` implements that port using
trusted tenant/project context and deterministic product services.

Selected published skill versions are projected as immutable packages beneath
`/skills/project/<slug>/`. Deep Agents may use `ls` and `read_file` against this
backend. Writes, edits, deletion, execution, and paths outside the projection
remain denied.

## Options considered

1. Import Deep Agents directly throughout tools and services. Rejected because
   framework concerns and product authority would remain entangled.
2. Mirror the entire Deep Agents API behind a large wrapper. Rejected because it
   would duplicate the framework and drift from its supported extension points.
3. Use a small reusable mechanism package plus an application composition root.
   Accepted because it preserves native Deep Agents behavior and gives both
   packages narrow, testable ownership.

## Consequences

- AI engineers can evolve prompts, retrieval, tools, middleware configuration,
  skills, subagents, and evaluation without editing product persistence code.
- Backend engineers can evolve authorization and canonical services behind a
  typed port without importing Deep Agents.
- The harness package can be tested and reused independently, but its compatibility
  range must remain aligned with the pinned Deep Agents release.
- Capability moves are hard cutovers; obsolete provider, state, middleware, tool,
  and runtime modules are removed rather than retained as shims.

## Security invariants

Tenant and project scope always originate in trusted runtime context and are
captured by the backend adapter. Source text remains evidence, not instructions.
Skill projection is read-only and path-bounded. Agent mutations remain proposals;
acceptance, publication, authorization, and canonical persistence remain
deterministic application commands.

## Validation

`backend/tests/test_reusable_agent_harness.py` proves concurrent budgets, tool
visibility, skill discovery reads, traversal denial, and mutation denial.
`backend/tests/test_optional_provider_contracts.py` compiles and invokes the
pinned Deep Agents graph and asserts primary/subagent skill wiring. Existing
retrieval, provider, trajectory, tenant-isolation, proposal, and checkpoint tests
remain required.
