# Phase 03 — Primary agent foundation

## Checklist

- [ ] `IMPL-03-001` Pin Deep Agents/LangGraph dependencies after reference/API verification.
- [x] `IMPL-03-002` Implement trusted runtime context, project agent state, checkpoint seam, and backend routing.
- [x] `IMPL-03-003` Central agent runtime boundary, versioned prompt, and read/proposal tool registry.
- [x] `IMPL-03-004` Create/reuse `project:{project_id}:primary` and run/message command path.
- [x] `IMPL-03-005` Planning/todo and normalized durable event/SSE projection.
- [ ] `IMPL-03-006` Cancellation, provider retry/errors, compaction/offload, dangling-call recovery.
- [x] `IMPL-03-007` Read-only UI/API conversation: source questions and project guidance.
- [ ] `IMPL-03-008` Trajectory, restart/resume, long-context, budget, tenant/tool red-team evaluations.

## Exit gate
The local deterministic runtime demonstrates the same persistent thread, grounded answers, proportional planning, durable replay/SSE, and boundary restrictions. A verified Deep Agents/Postgres deployment adapter is still a release gate.
