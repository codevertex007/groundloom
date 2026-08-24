# ADR-018: FastAPI BFF owns the stable public contract

**Status:** Accepted

## Decision
Frontend talks to FastAPI product DTOs/SSE. Deep Agents/LangGraph execution may run behind workers or Agent Server, but framework schemas are private.

## Consequences
Mapping code is required; runtime/deployment can change without rewriting the frontend.

## Validation
OpenAPI/event contract tests and checks that no checkpoint/provider objects leak publicly.
