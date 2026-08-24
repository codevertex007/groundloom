# Phase 04 — Skills, memory, and subagents

## Checklist

- [x] `IMPL-04-001` Skill package storage, versioning, resolver, scoped backend projection.
- [x] `IMPL-04-002` Validation/publish workflow, role/approval, starter packages.
- [x] `IMPL-04-003` Dedicated `/skills/ai-drafts` draft-only author boundary; local output is explicit deterministic scaffolding and configured external providers fail clearly until wired.
- [x] `IMPL-04-004` Typed scoped memory service/projection and approval/audit policy.
- [x] `IMPL-04-005` Specialist task contract and bounded source/outline/module delegation records.
- [x] `IMPL-04-006` Dynamic task execution with durable status, parent reconciliation, and a bounded leased delegated-task worker; local specialist execution is deterministic and production specialist models remain configured adapters.
- [x] `IMPL-04-007` Parent reconciliation and bounded partial retry/idempotency endpoints with durable audit/outbox evidence.
- [x] `IMPL-04-008` Skill pinning/memory isolation and delegation retry/reconciliation trajectory test coverage, including standalone worker recovery; live provider specialist trajectory remains deployment evidence.

## Exit gate
Local gate passes for scoped/pinned skills and memory, controlled publication, bounded delegation, and retry consumption by the standalone worker. Live provider specialist trajectory remains deployment evidence.
