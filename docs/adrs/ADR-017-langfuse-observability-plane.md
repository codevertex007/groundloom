# ADR-017: Langfuse as observability and evaluation plane

**Status:** Accepted

## Decision
Send redacted traces, usage, feedback, datasets, and evaluation results through a versioned adapter; never query/write Langfuse storage as product state.

## Consequences
Adapter failure must be fail-safe for product execution and visible operationally. Trace sampling/redaction policy is required.

## Validation
Metadata, hierarchy, redaction, outage, retry/buffer policy, cost attribution, and data-deletion tests.
