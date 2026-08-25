# Quality and evaluations component

Owns rubric/evaluator versions, validation executions, findings, review items/overrides, evaluation datasets/results, and feedback references. Deterministic validators and semantic graders share a structured finding model but remain distinguishable. The deterministic local grader is mandatory for known invariants; an optional OpenAI-compatible structured evaluator is bounded and provider-versioned.

Findings include severity, category, affected version/module/block/claim, evidence, validator version, suggested action, and status. Overrides require permission/reason and never erase original findings.

Required tests: deterministic validator coverage, grader schema/iteration cap, provider ordering and malformed-output handling, contradictory graders, override audit, version pinning, feedback linkage, redaction, regression dataset promotion, and quality control-plane isolation from interactive execution.
