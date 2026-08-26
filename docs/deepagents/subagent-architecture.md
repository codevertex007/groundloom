# Subagent architecture

The primary agent delegates only bounded, context-isolated work.

## Implemented specialists

`backend/app/ai/subagents/specs.py` registers three LangGraph `SubAgent` specs, each with its own scoped tool subset and prompt:

| Subagent | Output | Core constraints |
|---|---|---|
| Source researcher | `EvidenceBundle` | Read-only, authorized sources, no drafting |
| Module writer | Typed module draft | One owned module/task; cited claims |
| Citation auditor | Audit findings | Read-only; never rewrites content |

Outline construction and quality review — originally scoped as separate `Outline architect` and `Quality reviewer` LLM subagents — are instead fulfilled by non-agent mechanisms: outline proposals are assembled directly from the primary agent's own tool calls and typed patch proposals, and quality review is the deterministic rubric evaluator (`backend/app/ai/evaluation/providers.py`, `backend/scripts/run_evals.py`) rather than a self-certifying model. An `Assessment writer` specialist remains unimplemented; project assessments are out of scope for the current vertical slice.

Use synchronous delegation for small dependent tasks, async for long independent tasks, and dynamic batches when module count is runtime-defined. Each task records parent run/todo, input refs, pinned config, ownership, tools, permissions, budget, status, result, and error.

The parent reconciles conflicts, checks results, updates todos, and decides targeted retry. Concurrency is capped. Cancellation is checked before every tool call and between every model turn, including inside a delegated subagent's own execution — Groundloom's policy, budget, and progress middleware is registered through deepagents' `HarnessProfile.extra_middleware`, the extension point the framework threads into every stack it assembles (main agent and declarative subagents alike), not just `create_deep_agent`'s own inline `middleware=` list, which only reaches the main agent. A subagent cannot commit canonical content or expand its scope.
