# Phase 06 — Quality, evaluation, and export

## Checklist

- [x] `IMPL-06-001` Deterministic block/structure/citation/policy validators and finding schema.
- [x] `IMPL-06-002` Versioned rubric/grader protocol, transparent deterministic baseline, and bounded LangChain ChatOpenAI/Pydantic structured semantic evaluator adapter; live provider quality baselines remain deployment-specific.
- [x] `IMPL-06-003` Review checklist, evidence, status, override/approval/audit APIs/UI.
- [x] `IMPL-06-004` Deterministic local evaluation runner and regression test; retrieval/trajectory/e2e release datasets remain external evidence.
- [x] `IMPL-06-005` Render template/version and export job/artifact domain.
- [x] `IMPL-06-006` Deterministic PDF/DOCX/Markdown/HTML render, preview, validation, storage/download locally.
- [x] `IMPL-06-007` Export idempotency and expiry fields.
- [x] `IMPL-06-008` Redacted evaluation observation adapter for local telemetry/Langfuse and JSON regression runner; live Langfuse feedback/promotion workflow remains deployment evidence.

## Exit gate
Local gate passes for evidence-linked deterministic validation, typed semantic-evaluator failure boundaries, and idempotent accepted-content export. Semantic evaluator quality baselines and external telemetry integration remain release work.

The export job now uses a durable leased worker in staging/production. Development
can run one inline pass for the credential-free quickstart or set
GROUNDLOOM_EXPORT_INLINE_LOCAL=false to exercise the queue worker.
