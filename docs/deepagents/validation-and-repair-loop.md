# Validation and repair loop

## Deterministic checks

Always enforce schema validity, block operation legality, base-version match, authorized source lineage, citation target existence, required structure, policy/safety rules expressible in code, size/budget limits, and forbidden content/tool references.

## Semantic checks

Versioned rubrics may assess evidence support, contradictions, clarity, audience fit, style, objective coverage, and assessment quality. Graders return structured findings with severity, affected block/claim, evidence, rationale, and repair suggestion.

## Repair policy

The primary agent repairs only failed scope, using original evidence and findings. Cap automatic iterations (default two) and stop early when checks pass or improvement stalls. Security/authorization failures are not repairable by prompting. Persist all validation attempts and show unresolved failures.

Acceptance can require deterministic checks while allowing reviewer override of configured semantic warnings. Overrides record actor, reason, policy/rubric version, and affected findings.
