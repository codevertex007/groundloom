# Agent evaluation specification

## Trajectory dimensions

- Correctly asks or skips clarification.
- Plans proportional to complexity and maintains accurate todos.
- Loads relevant skills without loading everything.
- Retrieves evidence before factual drafting.
- Chooses direct action versus delegation appropriately.
- Respects tool, tenant, memory, and permission boundaries.
- Reconciles subagent outputs and repairs only failed scope.
- Stops within budgets and produces useful partial/final output.
- Uses approvals and resumes the same thread correctly.

## Dataset families

Small direct edits; ambiguous briefs; large multi-module projects; conflicting sources; missing evidence; malicious document instructions; stale content versions; failed subagent; provider timeout; cancellation; role/tenant attacks; long-thread compaction; accepted/rejected feedback regressions.

Each case defines input fixture/version set, expected/forbidden tools, acceptable trajectory constraints, deterministic assertions, rubric, and cost/latency envelope. Evaluation results are compared by release/profile; a weighted average cannot hide a security or invariant failure.
