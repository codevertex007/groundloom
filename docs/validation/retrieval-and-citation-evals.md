# Retrieval and citation evaluations

Datasets cover exact fact, paraphrase, table/numeric, section-neighbor, multiple-source synthesis, conflicting versions, no answer, changed version, and malicious instruction text. Record corpus/source/chunk/embed/reranker versions.

Metrics: candidate recall@k, reranked precision@k, answerable/no-answer classification, citation precision/coverage, unsupported claim rate, page/block/offset correctness, contradiction handling, latency, and token/result size.

Release requires zero cross-tenant leakage and zero fabricated passage IDs. Quality thresholds are established from baseline in phase 02 and may tighten; regressions beyond tolerance block retrieval/model profile changes.
