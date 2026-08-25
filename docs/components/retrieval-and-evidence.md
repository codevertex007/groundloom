# Retrieval and evidence component

Pipeline: trusted authorization/selected-version filter → lexical and semantic
candidate search → deterministic hybrid score → rerank/neighbor expansion
adapters → overlap dedupe → bounded `EvidenceBundle`. The local adapter uses a
deterministic fixed-dimension hash embedding; deployment can select the
OpenAI-compatible embedding boundary and a pgvector-backed implementation
without changing product DTOs or citation lineage.

`EvidencePassage` contains passage ID, source/version/name, page, section path, block ID, offsets, text, and scores. Bundles include query, passages, conflicts, gaps, and retrieval version. The model may narrow but never broaden server-computed scope.

Persist citations to immutable passage/block lineage, not display labels. The
derived `SourceChunk.embedding_json` is rebuildable and never canonical state.
Required tests/evals: golden recall/precision, exact page/block navigation,
conflicting evidence, no evidence, version pinning, prompt-injection passages,
cross-tenant invented IDs, large-result bounds, provider/reranker failure, and
rebuild equivalence.
