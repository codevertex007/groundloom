# ADR-032: AI contribution boundary and externalized prompts

- Status: Superseded by ADR-033
- Date: 2026-08-25

## Context

The primary agent runtime, provider adapters, and prompt instructions were
mixed with backend compatibility surfaces, and AI activity presentation was
embedded in the main frontend screen. That made ownership unclear and made
prompt review harder without changing the product's harness-first architecture.

## Decision

Create `backend/app/ai/` as the implementation boundary for the agent runtime,
explicit middleware, scoped tools, subagent specifications, AI provider
adapters, evaluation/retrieval logic, prompt loader, and prompt package data.
Store system prompts as reviewed UTF-8 `.txt` assets loaded by an allowlisted
resource loader. Remove flat root-module facades so ownership is unambiguous.
Create `frontend/src/ai/` for focused agent-specific presentation components;
keep API transport and canonical screen composition outside it.

## Consequences

AI engineers can change prompts, middleware, tools, subagents, and provider
behavior in a focused package with targeted tests. Backend engineers own tenant
scope, persistence, deterministic commands, and workers. Prompt assets must be
included in package data and prompt changes must update the pinned prompt
version or document why the existing contract remains compatible. Cross-boundary
changes require contract and traceability updates.

## Security invariants retained

The primary agent remains project-scoped and adaptive. Sources remain untrusted
evidence. Tenant scope comes from trusted runtime context. Provider adapters and
frontend components do not gain authority to commit canonical content or access
unrestricted infrastructure.
