# ADR-009: Persistent project thread with Postgres checkpointing

**Status:** Accepted

## Decision
Use `project:{project_id}:primary` for the long-lived collaborator and durable Postgres checkpoints for interrupts, compaction, and resume.

## Consequences
Long-thread context management and agent-definition compatibility require explicit testing. Runs remain distinct audit units.

## Validation
Restart, reconnect, approval resume, compaction, dangling tool-call, and version compatibility tests.
