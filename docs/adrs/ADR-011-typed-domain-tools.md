# ADR-011: Typed domain tools instead of generic infrastructure tools

**Status:** Accepted

## Decision
Expose narrow, versioned, bounded tools that derive tenant identity from runtime context. Do not expose generic SQL, production shell, arbitrary object paths, or unrestricted network fetch.

## Consequences
More tool definitions, but authorization, evaluation, tracing, and model guidance are precise.

## Validation
Schema/auth/replay/size tests and red-team attempts to broaden scope or invoke nonexistent generic capabilities.
