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

The local adapter gate is the evidence boundary for development: 13 backend tests, Ruff, mypy, documentation validation, and the frontend production build pass; the browser smoke covers project creation, source-grounded drafting, proposal review, and acceptance. The unchecked production gates above remain intentionally open because this environment has no verified Deep Agents provider, Postgres/pgvector instance, external object storage, identity provider, Langfuse deployment, or release-owner approval.

A waiver names the exact gate, evidence, risk owner, expiry, compensating controls, and approval. Tenant isolation, unauthorized canonical mutation, and data-loss risks are not waivable for launch.
