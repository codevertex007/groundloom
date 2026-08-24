# Retrieval and evidence component

Pipeline: trusted authorization/selected-version filter → lexical and pgvector candidate search → rerank → neighbor expansion → overlap dedupe → bounded `EvidenceBundle`.

`EvidencePassage` contains passage ID, source/version/name, page, section path, block ID, offsets, text, and scores. Bundles include query, passages, conflicts, gaps, and retrieval version. The model may narrow but never broaden server-computed scope.

Persist citations to immutable passage/block lineage, not display labels. Required tests/evals: golden recall/precision, exact page/block navigation, conflicting evidence, no evidence, version pinning, prompt-injection passages, cross-tenant invented IDs, large-result bounds, reranker failure, and rebuild equivalence.
