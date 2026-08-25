# ADR-025: pgvector for the deployment retrieval index

**Status:** Accepted  
**Date:** 2026-08-25

## Decision

Keep embedding JSON as a rebuildable local/test representation and add a
PostgreSQL `source_chunk_embeddings` derived table backed by pgvector for
deployment retrieval. Migration `015_pgvector_source_embeddings` creates the
extension/table, workspace scope, dimensions, and supporting metadata index;
the existing service authorization and selected-source-version filter remain
the authority for retrieval scope.

The `auto` retrieval-index setting selects the local JSON store for SQLite and
the pgvector store for PostgreSQL. Production rejects an explicit local index.
The vector table accepts provider-specific dimensions and filters by the
stored dimension; an operator that needs an approximate nearest-neighbor index
must pin a dimension and add the corresponding pgvector index in the target
deployment after measuring its corpus and provider profile.

## Rationale and consequences

This keeps local development credential-free and makes derived indexes
rebuildable while allowing production semantic candidate search to happen in
the database instead of loading every embedding into application memory. Both
representations are derived; source binaries, normalized blocks, citations,
and accepted content remain canonical elsewhere. Provider/database failures
are translated to bounded retryable errors and never expose SQL, credentials,
or provider response details.

The migration requires pgvector to be available to the migration role (or
pre-installed by the database operator). PostgreSQL integration tests verify
the extension, table, and RLS boundary; capacity, ANN index selection, rerank
quality, and golden-corpus performance remain deployment evidence.
