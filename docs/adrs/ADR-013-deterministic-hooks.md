# ADR-013: Deterministic hooks and middleware surround the adaptive loop

**Status:** Accepted

## Decision
Authorization, tool visibility, schemas, idempotency, budgets, cancellation, validation, and tracing are enforced outside/model-independent of the chosen semantic trajectory.

## Consequences
Middleware order and hook coverage become security/correctness critical, but the primary agent retains agency.

## Validation
Bypass attempts and alternate trajectories must still trigger every applicable hook.
