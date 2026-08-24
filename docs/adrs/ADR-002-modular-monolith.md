# ADR-002: Modular monolith with independent workers

**Status:** Accepted

## Context
A solo-maintained product needs clear boundaries without distributed-system overhead.

## Decision
Use one repository/domain codebase with API, agent, ingestion, export, and maintenance process entry points. Extract services only for measured need.

## Consequences
Modules must enforce dependencies/import boundaries. Processes share releases but scale independently.

## Validation
Architecture tests prevent forbidden imports; load/deployment evidence shows worker independence.
