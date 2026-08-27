# Backend architecture assessment

- Status: Implemented assessment with prioritized follow-up
- Date: 2026-08-27
- Scope: `backend/`, `packages/groundloom-agent-harness/`, backend tests, workers, migrations, and their normative contracts

## System model

Groundloom is a modular monolith with separate API and worker processes. The
same SQLAlchemy product model and deterministic application commands are used
by both process types. PostgreSQL is canonical product state, LangGraph
checkpoints are agent execution state, object storage owns source/export bytes,
and lexical/vector indexes are derived projections.

The principal execution paths are:

1. HTTP request -> trusted `RuntimeContext` -> application command/query ->
   scoped SQL/object-store mutation -> audit/outbox commit -> response DTO.
2. Source upload -> immutable `SourceVersion` -> scan -> parse/OCR -> normalized
   `SourceBlock` -> recursive derived chunks -> embedding/vector index -> ready.
3. Project message -> durable `AgentRun` -> inline local runtime or leased agent
   worker -> one persistent project Deep Agent -> scoped tools/subagents ->
   proposal records and durable public events.
4. Human decision -> deterministic approval/patch command -> immutable canonical
   version; model execution never commits canonical content directly.
5. Export/index/delegation/deletion jobs -> row-locked lease claim -> idempotent
   worker processor -> audit/outbox completion or typed failure.

## Ownership map

| Layer | Location | Responsibility |
|---|---|---|
| Transport/composition | `backend/app/main.py`, `backend/scripts/` | FastAPI lifecycle/routes, DTO adaptation, process entrypoints |
| Deterministic application services | `backend/app/services.py`, `backend/app/application/` | Authorization-aware use cases, audit/events/idempotency, run/job orchestration |
| Agent orchestration | `backend/app/ai/` | One `create_deep_agent` composition root, prompts, tools, specialist specs, runtime contracts |
| Reusable harness | `packages/groundloom-agent-harness/` | Groundloom-independent middleware, budgets, cancellation, safe stream projection, skill backend |
| Authorized AI bridge | `backend/app/integrations/ai/` | Product-owned implementation of the model-facing service port, scoped retrieval/indexing |
| External/derived infrastructure | `backend/app/integrations/documents/`, `integrations/exports/`, object/OCR/scanner/vector modules | Parsing, splitting, rendering, storage, providers, derived indexes |
| Persistence contracts | `models.py`, `migrations.py`, `db.py` | Canonical schema, forward migration, RLS/session scope |
| Interface contracts | `schemas.py`, `ai/contracts.py`, `ai/ports.py` | HTTP DTOs and model-facing capability types |

## Architectural findings and decisions

### High impact, addressed in this change

| Current state | Problem | Architecture/implementation | Validation |
|---|---|---|---|
| Initial ingestion and rebuild independently created one truncated chunk per block. | Long blocks lost semantic coverage and the two index paths could drift. | `integrations/documents/chunking.py` uses LangChain `RecursiveCharacterTextSplitter`; `integrations/ai/indexing.py` is the single derived-index builder used by ingestion and rebuild, with bounded embedding batches. | Multi-chunk rebuild-equivalence regression plus provider/index tests. |
| PostgreSQL retrieval loaded every selected block and every JSON embedding even after bounded pgvector search. | Production query memory/latency scaled with the entire selected corpus. | PostgreSQL now unions bounded semantic and lexical candidates, loads their immediate neighbors, and fetches only the selected chunk vectors. SQLite retains an explicit local-only scan. | Retrieval/vector tests and deployment-shaped pgvector gate. |
| Retrieval represented one embedding per block. | Multiple derived chunks collapsed nondeterministically to the final row in local retrieval. | Retrieval candidates carry all chunk embeddings and use the maximum semantic similarity per immutable block. | Multi-chunk and deterministic retrieval tests. |
| Deep Agents implicitly added its general-purpose subagent. | An undocumented fourth delegate inherited the parent tool surface, bypassing the reviewed specialist inventory. | The provider `HarnessProfile` disables the implicit general-purpose subagent; only source researcher, citation auditor, and module writer remain. | Pinned graph/profile and real delegation tests. |
| Agent patch idempotency used only summary text, while `create_patch` ignored the supplied idempotency key. | Distinct proposals could collide, and exact retries created duplicate patches. | The authorized adapter hashes the complete bounded proposal; `create_patch` now resolves/stores the workspace idempotency record transactionally. | Exact replay and same-summary/different-body regression. |
| Worker claims selected rows before leasing without a PostgreSQL lock. | Concurrent workers could claim the same queued work. | Every lease query uses `FOR UPDATE SKIP LOCKED`; SQLite continues as the single-process local adapter. | Existing worker replay tests; concurrent deployment execution remains a release-load gate. |
| Audit/event/idempotency/health/checkpoint code lived at the top of the cross-domain service module. | Cross-cutting application policy had no clear owner and transport code imported a god-module surface. | Cohesive modules under `app/application/` now own those capabilities; API and outbox entrypoints import them directly. | Audit, health, checkpoint, outbox, and full backend tests. |
| Parsers and binary export renderers lived inside `services.py`. | Infrastructure details were mixed with application use cases. | Parsing and rendering moved to explicit `integrations/documents/` and `integrations/exports/` adapters; public behavior is unchanged. | Source/OCR/export security tests. |

### Framework capability audit

| Concern | Decision |
|---|---|
| Agent construction | Keep native `create_deep_agent` at one composition root. Do not wrap the factory. |
| Middleware/subagents | Keep native `HarnessProfile.extra_middleware` so policy, cancellation, budgets, and progress reach declarative subagents. Disable the implicit general-purpose delegate. |
| State/persistence | Keep native LangGraph checkpointers for configured providers and `thread_id` scoped project execution. PostgreSQL product state remains separate. |
| Human approval | Keep deterministic product approval records for the current proposal-only tool surface. Native interrupts become necessary if a future model-visible tool can perform a guarded side effect. |
| Skills | Keep the custom backend because it is an authorized immutable projection implementing Deep Agents' `BackendProtocol`; generic filesystem backends would broaden scope. |
| Retrieval | Keep Groundloom's typed retrieval service/repository because tenant scope and immutable citation lineage are domain rules. Reuse the framework splitter only at the generic chunking seam. |
| Model/provider calls | Use dedicated LangChain provider integrations for embeddings, Cohere reranking, semantic grading, and one bounded provider-neutral skill-author call; retain only bounded product validation and typed redacted error translation. |
| Structured output | Use LangChain model-level structured output with Pydantic semantic-grade and skill-draft schemas, and LangChain `BaseTool` values with bounded Pydantic arguments for every model-facing tool. Use a direct model call rather than an agent when one typed result requires no tools or adaptive loop. |
| Streaming/tracing | Keep native LangGraph `messages`/`updates` streaming and safe projection. Deep Agents/LangSmith tracing remains provider/environment-driven; product-visible progress stays in durable events. |

## Remaining prioritized work

1. **P1 — continue splitting application use cases by capability.** Source
   ingestion/indexing/passage services now live in `application/sources.py`, but
   `services.py` remains the largest ownership hotspot. Move projects/runs,
   content, skills, exports, and retention into cohesive application modules one
   vertical slice at a time, updating all callers directly and avoiding
   compatibility shims.
2. **P1 — split transport routers.** `main.py` should become only the FastAPI
   composition root; route groups should own projects/runs, sources/retrieval,
   skills/memory, content/export, and operations. Route modules must call
   application services rather than perform ORM decisions themselves.
3. **P1 — make transaction ownership uniform.** Commands should commit once at
   the outer application boundary. Current service-level commits are preserved
   to avoid a broad behavioral rewrite but complicate multi-command atomicity.
4. **P1 — harden concurrent sequences.** Public-event sequence allocation and
   create-if-absent idempotency rely on uniqueness plus application checks; add
   bounded conflict retry or database-side allocation for high concurrency.
5. **P2 — replace generic model output maps where they cross stable boundaries.**
   Internal retrieval is typed, but several application DTO builders still use
   unconstrained dictionaries.
6. **Release evidence.** Run concurrent multi-worker lease tests, live provider
   long-context/compaction and resume trajectories, production LangSmith trace
   inspection, and the complete PostgreSQL/RLS/pgvector/S3 gate.

These items are deliberately ordered by dependency and risk. The current
change establishes their target seams without attempting an unsafe all-at-once
rewrite of the behavior-heavy service and route modules.
