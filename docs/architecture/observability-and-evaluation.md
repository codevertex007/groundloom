# Observability and evaluation architecture

Langfuse receives redacted, versioned traces through an adapter. Recommended hierarchy:

```text
groundloom_project_run
  primary_agent_loop
    project_context
    skill_load
    retrieval_tool
    subagent[type]
    proposal_tool
    validation_tool
    repair_iteration
    approval_wait
```

Attach workspace/project/run/module IDs, hashed pinned input sets, prompt/tool/retrieval/evaluator versions, model/provider, release SHA, latency, token/cost, status, and error class. Never write directly to Langfuse storage.

Evaluation layers: deterministic contracts; retrieval lineage; component outputs; agent trajectories; end-to-end scenarios; online proposal decisions and corrected citations. Grader prompts/rubrics are versioned. Reviewed failures become regression examples through a separate quality control plane, not automatic mutation of production skills or memory.
