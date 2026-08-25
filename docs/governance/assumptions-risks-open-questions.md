# Assumptions, risks, and open questions

## Accepted working assumptions

- Backend: Python, FastAPI, Deep Agents/LangGraph, Postgres with pgvector, S3-compatible object storage, Langfuse.
- Initial deployment: modular monolith with separate agent, ingestion, and export worker processes.
- Canonical authoring: typed blocks with immutable versions.
- Streaming: normalized SSE with durable replay.
- Initial collaboration: one active mutation turn per project thread; optimistic concurrency for content.
- The UI attachment is the product-design baseline; intentional deviations require a recorded decision.

## Decisions required before affected phases

| ID | Question | Needed by | Default if not changed |
|---|---|---|---|
| OQ-001 | First export formats? | Phase 06 | PDF + DOCX |
| OQ-002 | Supported source types in v1? | Phase 02 | PDF, DOCX, TXT; URL deferred |
| OQ-003 | Identity provider? | Phase 01 | Adapter with local dev identity; production provider undecided |
| OQ-004 | Model providers and exact models? | Phase 03 | Provider-neutral adapter; configure at deployment |
| OQ-005 | Queue/worker technology? | Phase 02 | Postgres-backed job lease initially |
| OQ-006 | Required content block types per project type? | Phase 05 | Core generic block set in component spec |
| OQ-007 | Retention periods? | Phase 08 | Workspace-configurable with conservative defaults |

## Principal risks

- Context growth in long project threads: mitigate with manifests, bounded evidence, offload, summaries, and regression tests.
- Source prompt injection: treat documents as data, isolate trusted instructions, restrict tools, and test malicious fixtures.
- Duplicate effects after replay: idempotency keys, unique constraints, outbox, and failure-injection tests.
- Agent appears busy without useful progress: expose todos and actual tool/subagent/job state; measure time to useful artifact.
- Citation correctness degrades across edits: immutable lineage, proposal validation, and regression datasets.
- Documentation drift during autonomous implementation: root `AGENTS.md`, traceability gates, and same-change documentation policy.
- Framework API drift: pin dependencies and check `docs/ref/deepagents/` plus current official docs before upgrades.
- Local execution uses explicit deterministic adapters by default. The main development environment does not install the optional provider extras; an isolated probe environment installed the pinned `deepagents`, Postgres checkpoint, S3, Langfuse, and provider packages and compiled a fake-model graph. Live credentials/service evidence remains open.
- Ingestion uses a durable leased job/state-machine processor and `ingestion_worker.py --once`; the local API completes small jobs synchronously through that same processor. Export uses the same durable leased state machine; the development adapter runs one bounded inline pass by default for quickstart usability, while GROUNDLOOM_EXPORT_INLINE_LOCAL=false exercises the standalone worker. Backup/restore, load, OCR-provider capacity, and failure-injection exercises remain release work; OCR has an explicit local refusal and HTTP sidecar adapter.

## External release-evidence register

These items are intentionally outside credential-free local validation. Each
has an accountable owner, a compensating local control, and a review point so
the release boundary is explicit rather than silently waived.

| Risk/evidence item | Owner | Impact | Compensating control now | Required evidence / review |
|---|---|---|---|---|
| Live model and Deep Agents provider execution | Platform/AI | Provider-specific tool, budget, retry, and long-context behavior may differ from the pinned harness probe | Local deterministic runtime, pinned Deep Agents compile/stream probe, bounded recursion limit, typed provider outage handling | Staging provider smoke and trajectory set before staging sign-off |
| Production identity and tenant authorization | Security/Platform | Incorrect issuer, claims, key rotation, or role mapping could cross tenant boundaries | Signed HMAC adapter, trusted runtime scope, service/tool checks, PostgreSQL forced RLS deployment tests | OIDC/JWT integration, key rotation, and cross-tenant penetration test before launch |
| Langfuse delivery and telemetry retention | Observability/Platform | Missing traces or incorrect retention can impair diagnosis and privacy controls | Redacted local telemetry, bounded Langfuse adapter failure behavior, no product-state dependency | Live delivery, dashboard/alert review, retention test before staging sign-off |
| OCR/scanner provider capacity and degradation | Document Platform | Scanned or unsafe sources may remain unavailable or queue during provider outage | Explicit HTTP adapters, bounded timeouts, typed outage errors, terminal quarantine, local non-success behavior | Provider capacity, outage/replay, and malicious-fixture exercise before launch |
| PostgreSQL/object-store encrypted backup and isolated restore | Operations | Data loss or unrecoverable checkpoints could violate recovery objectives | Checksum-backed local restore, S3 AES-256/KMS startup/write guards, migration/checkpoint verification | Encrypted Postgres/object-store restore rehearsal with measured RPO/RTO |
| Production load, soak, rollback, and worker death recovery | Operations | Queue growth, cost overruns, or rollback incompatibility could interrupt service | Bounded leases/retries, heartbeats, budgets, health/readiness, deployment-shaped integration suite | Staging soak, failure injection, expand/migrate/contract rollback rehearsal |
| Accessibility manual review and launch authorization | Product/Accessibility | Automated axe checks cannot prove screen-reader and keyboard usability in all journeys | Semantic React tests, keyboard states, axe serious/critical scan, typed error states | Screen-reader review and release-owner approval before pilot |

## Naming note

Groundloom is a working name. Conduct legal, domain, and package-name clearance before public launch.
