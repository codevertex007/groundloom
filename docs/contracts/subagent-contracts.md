# Subagent contracts

Common task envelope includes task/parent run/todo/project IDs, immutable input refs, objective, expected structured schema, allowed tools/skills, permission profile, model profile, budget/deadline, cancellation token, and idempotency key.

Common result includes task/status, structured artifact/evidence refs, concise summary, assumptions/gaps/conflicts, validation status, usage, and typed error. Do not return hidden reasoning or unbounded inspected content.

Ownership is explicit: module writer owns only assigned draft scope; researcher returns evidence only; auditor returns findings only. The parent validates/reconciles. Dynamic batch task count and concurrency are capped, task state is durable, and completed tasks are reused on parent replay.
