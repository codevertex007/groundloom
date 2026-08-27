# Retrieval and evidence component

Pipeline: trusted authorization/selected-version filter → lexical and semantic
candidate search → deterministic hybrid score → bounded rerank → same-version
neighbor expansion → overlap dedupe → bounded `EvidenceBundle`. The local adapter uses a
deterministic fixed-dimension hash embedding; deployment can select the
LangChain `OpenAIEmbeddings` boundary and a pgvector-backed implementation
without changing product DTOs or citation lineage.
Optional provider reranking uses LangChain `CohereRerank` with the Cohere v2
client; Groundloom still validates complete finite scores and restores them to
the original authorized candidate order.

`EvidencePassage` contains passage ID, source/version/name, page, section path, block ID, offsets, text, and scores. Bundles include query, passages, conflicts, gaps, and retrieval version. The model may narrow but never broaden server-computed scope. SQLite uses the rebuildable JSON vector representation; PostgreSQL `auto` mode uses the pgvector derived table for semantic candidates and reports `hybrid.pgvector.v2`. Results are normalized-deduplicated and capped by the caller's bounded limit; strong hits may contribute one adjacent block from the same immutable source version.

Persist citations to immutable passage/block lineage, not display labels. The
derived `SourceChunk.embedding_json` and PostgreSQL
`source_chunk_embeddings` representations are rebuildable and never canonical
state.
Multiple chunks may represent one immutable block. Local scoring uses the
maximum cosine similarity across that block's chunk vectors. PostgreSQL first
unions bounded pgvector and lexical candidates, then loads those blocks and
their immediate same-version neighbors; it does not materialize every selected
chunk after ANN candidate search. Full selected-corpus scanning is limited to
the explicit SQLite development adapter.
Required tests/evals: golden recall/precision, exact page/block navigation,
conflicting evidence, no evidence, version pinning, prompt-injection passages,
cross-tenant invented IDs, large-result bounds, deterministic/provider reranker
failure, neighbor expansion, duplicate suppression, and rebuild equivalence.
