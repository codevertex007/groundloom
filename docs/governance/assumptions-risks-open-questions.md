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

## Naming note

Groundloom is a working name. Conduct legal, domain, and package-name clearance before public launch.
