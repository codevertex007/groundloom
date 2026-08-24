# ADR-024: PostgreSQL row-level tenant isolation

**Status:** Accepted  
**Date:** 2026-08-25

## Decision

Production PostgreSQL enables and forces row-level security on workspace-owned
product tables. Policies compare `workspace_id` with the transaction-local
`app.workspace_id` setting. Global starter skills may have a null workspace and
remain readable across authorized workspaces. Trusted leased workers use a
separate service-context marker for cross-workspace queue claims, while each
worker still scopes processing, mutations, and audit records to the run's
workspace.

The API derives the workspace only after trusted identity and membership
resolution, then sets the tenant context on the SQLAlchemy session. A session
event reapplies the transaction-local setting after every commit so a later
transaction cannot lose the boundary. SQLite keeps the same trusted context in
session metadata but does not execute PostgreSQL-specific SQL.

## Rationale and consequences

Service-level filters remain mandatory because RLS is defense in depth and does
not replace authorization. Forced policies protect against a missed repository
filter when the production application role is not a policy-bypassing database
owner. Health and migration operations remain separate infrastructure paths;
they do not receive end-user tenant context.

Migration `011_postgres_rls_tenant_isolation` is forward-only and idempotently
recreates the policies. Live policy behavior, role separation, and previous
release migration rehearsal still require a real PostgreSQL deployment gate.
