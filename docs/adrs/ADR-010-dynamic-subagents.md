# ADR-010: Dynamic bounded subagents

**Status:** Accepted

## Decision
Let the primary agent choose synchronous, async, or dynamic specialist delegation based on task boundaries rather than fixed per-module graph fan-out.

## Consequences
Need durable task state, concurrency caps, structured contracts, cancellation/steering, and parent reconciliation.

## Validation
Direct-versus-delegate trajectory cases, partial retry, concurrency, cancellation, scope, and duplicate-task tests.
