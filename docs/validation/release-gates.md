# Release gates

Release owner verifies:

- [ ] All targeted active requirements have passing proof in the matrix.
- [ ] Format/lint/type/unit/contract/integration/e2e/eval/accessibility gates pass.
- [ ] Retrieval/trajectory/content quality meets approved baselines without invariant failure.
- [ ] No unresolved critical/high security issue or tenant-isolation failure.
- [ ] Migration from previous release and fresh install pass; rollback/compatibility rehearsed.
- [ ] Backup/restore and key failure-injection scenarios pass.
- [ ] Performance/cost stays inside declared envelope.
- [ ] Production configuration, redaction, secrets, retention, alerts, dashboards, and runbooks are reviewed.
- [ ] Documentation, ADRs, contracts, examples, checklists, and code agree.
- [ ] Known limitations/open risks have owner, impact, mitigation, and review date.
- [ ] Staging smoke/soak and production smoke/rollback criteria are signed.

## Local release evidence

The local adapter gate is the evidence boundary for development: 77 backend tests (two optional-provider tests skip when extras are absent), Ruff, mypy, documentation validation, deterministic evaluation telemetry, signed-identity and short-lived artifact-capability tests, scoped local checkpoint persistence, role-bound RLS and pgvector policy generation through migrations 011/013/014/015, dedicated worker/migrator configuration checks, production API no-bootstrap and worker-session tests, checksum-backed backup/restore tests, explicit derived-index rebuild, deterministic/provider/pgvector embedding and reranker boundaries, structured semantic-evaluator provider boundaries, bounded neighbor expansion and duplicate suppression, a synthetic retrieval benchmark, delegation retry/reconciliation and trajectory tests, leased agent-worker dispatch, worker health/heartbeat and budget-stop tests, role-scoped cursor-paginated audit reads with read auditing, shared immutable-source deletion preservation, escaped untrusted export rendering, recursively redacted telemetry, bounded multipart upload reads, deterministic local and HTTP source-safety scanner/quarantine tests, 5 native frontend tests, 3 actual React component-rendering tests, 10 Playwright tests (9 semantic E2E/accessibility tests plus the pinned Windows visual-baseline test), and the frontend production build pass; the browser journey covers cursor-paginated project loading, project creation with active skill selection, source-grounded drafting, plan approval/resume, proposal review, acceptance/rejection with canonical safety, AI skill scope filtering/forking/author/repair/publication, permission-denied rendering, settings persistence, command-palette navigation, run status controls, source version history/revision upload, source upload/readiness, evidence selection, exact citation navigation, dropped-stream reconnect, and serious/critical axe violations. A disposable Docker deployment-shaped suite also passes Postgres/RLS/pgvector/checkpoint/S3 integration tests. The unchecked production gates above remain intentionally open because this environment has no live Deep Agents provider, identity provider, Langfuse deployment, production restore rehearsal, load report, or release-owner approval.

A waiver names the exact gate, evidence, risk owner, expiry, compensating controls, and approval. Tenant isolation, unauthorized canonical mutation, and data-loss risks are not waivable for launch.

Detailed local command output and the external-evidence boundary are recorded in
[`release-candidate-evidence.md`](release-candidate-evidence.md).
