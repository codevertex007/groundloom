# Phase 02 — Source ingestion and retrieval

## Checklist

- [x] `IMPL-02-001` Upload/finalization, immutable source/version records, scoped object keys, type/size checks.
- [x] `IMPL-02-002` Durable leased ingestion job and idempotent stage state machine; local API and `ingestion_worker.py --once` use the same processor.
- [x] `IMPL-02-003` PDF/DOCX/TXT/Markdown parsers and normalized page/block/chunk schema; OCR remains an adapter extension.
- [x] `IMPL-02-004` Versioned deterministic chunking/indexing with an explicit scoped, idempotent rebuild worker that persists deterministic local or configured-provider embeddings and mirrors deployment vectors into the scoped pgvector derived table through migration 015.
- [x] `IMPL-02-005` Authorized bounded hybrid lexical/semantic evidence search with selected-version filtering, deterministic/provider reranking, same-version neighbor expansion, duplicate suppression, and typed provider failure handling.
- [x] `IMPL-02-006` Passage read/navigation APIs and citation-lineage primitives.
- [x] `IMPL-02-007` Prompt-injection/sanitization signals and adversarial source fixture coverage.
- [x] `IMPL-02-008` Local replay/failure and security fixtures; production-scale golden retrieval/load/deletion exercise remains a release gate.

## Exit gate
A source can reach ready state, be searched only in authorized selected versions, navigate exact lineage, rebuild derived lexical/embedding indexes through the queued worker, and recover safely from every stage failure. Deployment-shaped pgvector schema/search and RLS are covered by the opt-in integration path; high-scale ANN/reranking, OCR, and golden-corpus quality evidence remain deployment-specific.
