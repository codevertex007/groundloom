# Phase 02 — Source ingestion and retrieval

## Checklist

- [x] `IMPL-02-001` Upload/finalization, immutable source/version records, scoped object keys, type/size checks.
- [ ] `IMPL-02-002` Durable leased ingestion job and idempotent stage state machine.
- [x] `IMPL-02-003` PDF/DOCX/TXT/Markdown parsers and normalized page/block/chunk schema; OCR remains an adapter extension.
- [x] `IMPL-02-004` Versioned deterministic chunking/indexing; embedding/rebuild worker remains open.
- [x] `IMPL-02-005` Authorized bounded lexical evidence search with selected-version filtering.
- [x] `IMPL-02-006` Passage read/navigation APIs and citation-lineage primitives.
- [x] `IMPL-02-007` Prompt-injection/sanitization signals and adversarial source fixture coverage.
- [ ] `IMPL-02-008` Golden retrieval dataset, latency/load, failure/replay/deletion tests.

## Exit gate
A source can reach ready state, be searched only in authorized selected versions, navigate exact lineage, rebuild derived indexes, and recover safely from every stage failure.
