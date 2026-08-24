# ADR-007: Immutable versions and run pinning

**Status:** Accepted

## Decision
Runs pin source, skill, project config, prompt, tool, model profile, retrieval, template, and evaluator versions relevant to output.

## Consequences
Storage/version lifecycle is more explicit; historical behavior remains diagnosable when defaults change.

## Validation
Change dependencies after a run and prove historical provenance/output references remain unchanged.
