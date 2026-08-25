# ADR-026: bounded retrieval reranking and context expansion

**Status:** Accepted  
**Date:** 2026-08-25

## Decision

Retrieval uses versioned `hybrid.v2` behavior: authorize and filter selected
source versions, retrieve bounded lexical/semantic candidates, rerank at most
100 candidates, expand one same-version neighboring block around sufficiently
strong hits, deduplicate normalized duplicate passages, and return the final
bounded bundle. PostgreSQL uses the same pipeline after pgvector candidate
search and reports `hybrid.pgvector.v2`.

The default reranker is deterministic overlap/phrase scoring. A narrow
Cohere-compatible HTTP adapter may be configured through the reranker settings;
outages, rejected requests, incomplete results, and malformed scores become
typed redacted errors. Reranking never changes authorization, source-version
selection, or citation lineage.

## Consequences

Neighbor context improves passage usefulness without allowing the model to
broaden scope. Stable version identifiers and pinned reranker/index settings
make retrieval changes observable and reproducible. Candidate, neighbor, and
result limits remain explicit to protect latency and token budgets. Quality
thresholds, approximate-nearest-neighbor indexes, and provider-specific
reranker baselines remain deployment evaluation work.
