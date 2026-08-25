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

The local gate includes `DeterministicSemanticGrader` and a JSON evaluation
runner. It checks required rubric terms and citation presence transparently; it
does not claim model-level semantic quality. A deployment may provide a pinned
semantic grader through the same narrow interface and must publish its rubric,
evaluator version, dataset hash, and regression report. Langfuse integration is
lazy-loaded through the telemetry adapter and remains optional locally.
Evaluation reports are emitted through `record_evaluation`; the local adapter
stores a bounded recursively redacted event and Langfuse receives the same
observation via its adapter. Nested lists/maps are treated as untrusted
telemetry payloads, and no evaluator can mutate a skill, memory item, or
canonical content.
