# ADR-006: Agent proposals are separate from deterministic commits

**Status:** Accepted

## Decision
Agents may create validated outline/content/skill proposals. Authorized domain commands accept, reject, publish, or conflict them. Agents do not mutate canonical accepted content directly.

## Consequences
More records/UI states, but safe review, replay, audit, and optimistic concurrency become possible.

## Validation
Reject immutability, duplicate accept, stale-base conflict, permission, and audit tests.
