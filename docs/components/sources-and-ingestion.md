# Sources and ingestion component

Owns source metadata, immutable versions, upload finalization, processing jobs/stages, normalized blocks/assets, and readiness. Original bytes are stored once per version; derived chunks/embeddings are rebuildable and configuration-versioned.

Deterministic stages: upload finalize → malware/type validation → parse/OCR → normalize page-aware blocks → chunk/enrich → embed/index → quality checks → ready. Each stage is idempotent by source version + processor configuration and supports bounded retry/terminal quarantine.

Tools expose manifests and passages only after service authorization. Required tests: unsafe files, spoofed MIME, parser failure, duplicate finalize, stage replay, version replacement, job lease death, lineage, deletion, cross-tenant access, and pinned old-version reproducibility.
