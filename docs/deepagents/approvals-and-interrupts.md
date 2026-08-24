# Approvals and interrupts

Approval use cases: outline/plan when configured, organization skill publication, memory writes when configured, export/external actions, and any future irreversible integration.

An approval record contains type, requested action, human-readable summary, exact proposed payload/version IDs, requester/run/thread, required role, expiry, status, actor, decision time, reason/edit, and idempotency key.

Use Deep Agents/LangGraph interrupt with a persistent checkpointer. Resume the same thread and validate that proposal, permissions, policy, and relevant base versions are still current. Approval authorizes only the exact recorded action; modified payloads require new approval. Duplicate approvals/declines are idempotent. Expired/revoked membership returns a typed denial.

Do not expose hidden chain-of-thought. Present concise rationale, evidence, consequences, and diff necessary for an informed decision.
