# ADR-016: Bounded semantic validation and targeted repair

**Status:** Accepted

## Decision
Combine mandatory deterministic checks with versioned semantic rubrics. Automatic repair targets findings and stops after a small configured cap or stalled improvement.

## Consequences
Quality is inspectable without unbounded self-reflection. Human override remains explicit/audited.

## Validation
Pass/fail, iteration cap, stalled repair, non-repairable policy failures, override, and rubric-version tests.
