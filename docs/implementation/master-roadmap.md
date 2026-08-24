# Master implementation roadmap

Execute phases in order unless dependency map and an ADR justify parallel work. Each phase exits only when its checklist, tests, docs, and evidence are complete.

| Phase | Outcome |
|---|---|
| 00 | Executable repository, contracts, quality gates, local infrastructure |
| 01 | Tenant-safe domain/persistence/API backbone |
| 02 | Versioned source ingestion and grounded retrieval |
| 03 | Persistent primary Deep Agent with read-only collaboration |
| 04 | Skills, memory, middleware, and specialist delegation |
| 05 | Typed outlines/content, proposals, review, acceptance |
| 06 | Quality/evaluation and deterministic exports |
| 07 | Complete UI integration and resilient streaming UX |
| 08 | Security, reliability, operations, performance hardening |
| 09 | Production readiness, staged rollout, release evidence |

Use one branch/change set per reviewable vertical slice. A phase exit report updates `validation/requirements-test-matrix.md`, records metrics/deviations, and identifies the next safe checklist item.
