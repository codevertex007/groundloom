# Phase 03 — Primary agent foundation

## Checklist

- [x] `IMPL-03-001` Pin optional Deep Agents/LangGraph/provider dependencies after reference/API verification; live provider installation remains a deployment gate.
- [x] `IMPL-03-002` Implement trusted runtime context, project agent state, checkpoint seam, and backend routing.
- [x] `IMPL-03-003` Central agent runtime boundary, versioned prompt, and read/proposal tool registry.
- [x] `IMPL-03-004` Create/reuse `project:{project_id}:primary` and run/message command path.
- [x] `IMPL-03-005` Planning/todo and normalized durable event/SSE projection, including bounded provider message/update stream projection.
- [x] `IMPL-03-006` Cancellation and bounded provider retry/errors, including cancellation checks between provider stream chunks; compaction/offload and live dangling-call recovery remain deployment evidence.
- [x] `IMPL-03-007` Read-only UI/API conversation: source questions and project guidance.
- [x] `IMPL-03-008` Local trajectory, tenant/tool red-team, replay/resume, and bounded-runtime evidence; long-context/provider-budget evaluation remains deployment work.
- [x] `IMPL-03-009` Persist redacted per-run usage/budget metadata and enforce the plan-approval interrupt/resume contract for configured projects.
- [x] `IMPL-03-010` Dispatch staging/production runs to a leased durable agent worker and preserve inline local/test execution as an explicit adapter mode.
- [x] `IMPL-03-011` Disable the framework's implicit general-purpose delegate so the executable subagent surface is limited to the three audited specialist specs.

## Exit gate
The local deterministic runtime demonstrates the same persistent thread, grounded answers, proportional planning, durable replay/SSE, and boundary restrictions. A verified Deep Agents/Postgres deployment adapter is still a release gate.
