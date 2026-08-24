# Middleware stack

Construction is centralized in one factory/registry. The exact order is locked by tests and framework reference review.

Conceptual responsibilities:

1. Trusted runtime/project context hydration.
2. Tenant/path/tool permission policy.
3. Tool visibility/exclusion based on phase, role, and feature policy.
4. Skills and memory projection.
5. Filesystem/scratch and large-result offload.
6. Planning/todo behavior.
7. Summarization/context compaction.
8. Tool-call history repair/checkpoint compatibility.
9. Budgets, timeouts, cancellation, and bounded grader loops.
10. Redacted tracing/evaluation callbacks.

Do not infer actual framework order from this list: verify constructors and interaction details in `docs/ref/deepagents/`. Add a middleware only with a stated responsibility, ordering constraints, failure behavior, tests, and observability. Middleware may constrain trajectories but must not recreate a rigid semantic workflow.
