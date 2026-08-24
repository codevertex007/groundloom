# ADR-008: Postgres full-text plus pgvector for initial retrieval

**Status:** Accepted

## Decision
Begin with authorized metadata filtering, Postgres lexical/vector candidates, reranking, neighbor expansion, and bounded evidence bundles.

## Consequences
Operational simplicity for v1; a future specialized engine requires measured scale/quality evidence and migration ADR.

## Validation
Golden recall/precision, latency/load, isolation, version pinning, and rebuild tests.
