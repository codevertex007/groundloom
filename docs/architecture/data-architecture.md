# Data architecture

Postgres schemas/modules cover identity, projects, sources, skills, content, runs, quality, export, governance, checkpoints, and outbox. Use UUID/ULID-style opaque identifiers consistently; timestamps are UTC; records include created/updated actor metadata where mutable.

Key records are detailed in `components/`. Migrations are forward-only, reviewed, transactional where supported, and tested from an empty database plus the previous release snapshot. Large derived source chunks/embeddings may be rebuilt; originals, normalized lineage, accepted content, decisions, approvals, and audit records are protected.

Use database constraints for uniqueness, foreign keys, valid simple state invariants, idempotency, and optimistic version numbers. Application checks do not replace constraints. PostgreSQL migration `011_postgres_rls_tenant_isolation` forces row-level policies as defense in depth while retaining service authorization; SQLite uses the same session-context contract without RLS SQL.

Object keys are derived server-side from workspace/resource IDs and never accepted directly from models/users. Deletion tracks canonical, derived, checkpoint, trace/redaction, and object-store completion separately.
