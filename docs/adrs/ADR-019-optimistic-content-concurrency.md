# ADR-019: Optimistic concurrency for content commitment

**Status:** Accepted

## Decision
Proposals target a base version; accept succeeds only when expected current/base conditions hold, otherwise returns a conflict for regeneration/rebase/user choice.

## Consequences
No silent last-write-wins. UI and agent must handle conflicts explicitly.

## Validation
Concurrent proposal/accept, duplicate accept, stale base, and current-pointer transaction tests.
