# Subagent architecture

The primary agent delegates only bounded, context-isolated work. Initial specialists:

| Subagent | Output | Core constraints |
|---|---|---|
| Source researcher | `EvidenceBundle` | Read-only, authorized sources, no drafting |
| Outline architect | Structured outline proposal | Uses brief/evidence/skills; no persistence |
| Module writer | Typed module draft | One owned module/task; cited claims |
| Citation auditor | Audit findings | Read-only; never rewrites content |
| Assessment writer | Typed assessments | Objective coverage and evidence |
| Quality reviewer | Rubric result | Bounded, cannot self-certify security |

Use synchronous delegation for small dependent tasks, async for long independent tasks, and dynamic batches when module count is runtime-defined. Each task records parent run/todo, input refs, pinned config, ownership, tools, permissions, budget, status, result, and error.

The parent reconciles conflicts, checks results, updates todos, and decides targeted retry. Concurrency is capped. Cancellation/steering is durable. A subagent cannot commit canonical content or expand its scope.
