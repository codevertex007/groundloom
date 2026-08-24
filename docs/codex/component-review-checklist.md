# Component review checklist

- Responsibilities/boundaries match component and ADRs.
- API/tool/event/data schemas match contracts and examples.
- Tenant scope/auth applies at every boundary.
- Mutations are transactional/idempotent/audited.
- Versioning/concurrency/replay behavior is explicit.
- Errors are typed, safe, observable, and correctly retryable.
- Resource/context/output limits exist.
- Unit, contract, integration, security, failure, and relevant e2e/eval cases pass.
- Telemetry is useful and redacted.
- Migrations have compatibility/rollback strategy.
- Relevant docs, ADRs, traceability, checklists, and runbooks were updated.
- No placeholder/dummy implementation or silent fallback remains.
