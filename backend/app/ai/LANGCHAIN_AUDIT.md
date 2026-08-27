# LangChain capability audit

Status: implemented  
Date: 2026-08-27  
Scope: `backend/app/ai/` plus the reusable harness and document-indexing seams it composes

## Outcome

Groundloom now uses LangChain or Deep Agents wherever those frameworks already
own generic model plumbing. The removed hand-written provider HTTP path was the
largest avoidable maintenance burden: embeddings, Cohere reranking, the
semantic evaluator, and provider-backed skill authoring now use supported
integration packages, and every
model-facing Groundloom function is a LangChain `BaseTool` with a bounded
Pydantic input schema.

Custom code remains only where it represents Groundloom product policy,
authorization, durability, canonical state, or stable public contracts. A
framework abstraction must not be used merely to reduce line count if doing so
would move tenant scope or citation authority into model-controlled metadata.

## Complete capability matrix

| AI concern | Before | Framework capability | Decision after audit | Why |
|---|---|---|---|---|
| Primary LLM loop | Native `create_deep_agent` with a provider/model string | Deep Agents model resolution and LangChain agent loop | Keep native | Already framework-owned; another wrapper would duplicate resolution and streaming behavior. |
| Provider/model selection | Primary agent already uses `provider:model`; narrow calls were provider-specific or absent | LangChain `init_chat_model` | Reuse for provider-neutral direct calls | Skill author now follows the same provider/model convention; dedicated embeddings, reranker, and evaluator integrations retain their explicit configuration. |
| Chat messages/history | Deep Agents/LangGraph native message state | LangChain message types and LangGraph state | Keep native | Groundloom should not create a parallel conversation DTO inside the execution graph; only the public event projection stays custom. |
| Simple/structured model call | Manual chat-completions HTTP for semantic grading; skill author rejected every configured provider | `ChatPromptTemplate`, model-level typed structured output, and provider-neutral `init_chat_model` | Replaced | The evaluator and draft-only skill author now make bounded typed calls without local request/response plumbing. A one-result skill draft does not need an agent loop. |
| Embeddings | Manual embeddings HTTP and response ordering | `OpenAIEmbeddings.embed_documents` | Replaced | The integration handles API details; Groundloom retains fixed-dimension and finite-vector validation. |
| Reranking | Manual Cohere-compatible rerank HTTP and result ordering | `CohereRerank` over LangChain `Document` values | Replaced | The dedicated integration owns Cohere v2 transport; Groundloom restores scores to original candidate order. |
| Provider HTTP/retries | Shared `httpx.post` helper | Provider SDKs used by LangChain integrations | Deleted | Bespoke transport no longer tracks three provider APIs. SDK status metadata is translated into stable redacted product errors. |
| Prompt construction | Evaluator messages assembled as request dictionaries | `ChatPromptTemplate` and runnable composition | Replaced for model calls | Versioned assets remain package data; LangChain composes them with bounded runtime input. |
| Output parsing | Manual nested JSON indexing for the evaluator | Model-level Pydantic structured output | Replaced | Strict schemas now reject missing, extra, oversized, non-finite, or invalid enum values before they reach product services. |
| Model-facing tools | Nested plain callables inferred by Deep Agents | LangChain `@tool`, `BaseTool`, Pydantic `args_schema` | Replaced | Tool identity, descriptions, validation, and profile/exclusion behavior are explicit. |
| Tool execution loop | Deep Agents invokes tools and returns tool messages | LangChain/Deep Agents tool calling | Keep native | Groundloom owns authorization inside each service call, not a second home-grown dispatch loop. |
| Tool output/domain service | Authorized service returns bounded product dictionaries | LangChain serializes tool objects but does not own product DTOs | Keep custom | Output authority, tenant checks, idempotency, and proposal semantics belong to application services. |
| Agent construction | One `create_deep_agent` composition root | Deep Agents harness | Keep native | Correct layer for a persistent planning, skills, and subagent collaborator. |
| Specialist delegation | Declarative Deep Agents specs | Native subagent middleware and task tool | Keep native | Already framework-owned; the implicit general-purpose delegate remains disabled. |
| Planning/todos | Deep Agents profile behavior plus durable projections | Framework todo middleware | Keep native plus product projection | Product-visible progress still requires durable replayable events, not model percentages. |
| Skills | Read-only custom backend projection | Native skills middleware and backend protocol | Keep adapter, use native middleware | Generic filesystems would expose the wrong authority; this is the minimal authorized projection. |
| Stable memory | Approved Postgres memory exposed by a read tool | Deep Agents store/memory backends | Keep product memory | Approval, provenance, deletion, and tenant rules are canonical product state. |
| Retrieval service | Scoped hybrid ranking, lineage, neighbors, and dedupe | LangChain retrievers/vector stores | Keep service | Generic retrievers do not enforce selected immutable versions, RLS, passage IDs, or citation lineage. |
| Text splitting | Custom chunk logic | `RecursiveCharacterTextSplitter` | Already replaced | Generic splitting belongs in LangChain; source-version and derived-index ownership remain Groundloom-specific. |
| Document loading/parsing | Purpose-built bounded PDF, DOCX, TXT, and Markdown ingestion | LangChain document loaders | Keep product adapters | Malware/quarantine checks, immutable source-version lineage, MIME rules, OCR staging, and byte limits precede text extraction and are not generic RAG concerns. |
| Vector store | RLS-scoped pgvector plus local rebuildable representation | LangChain vector stores | Keep repository | Replacement would duplicate canonical schema and weaken workspace scope and block lineage. |
| Similarity/hybrid scoring | Small deterministic math functions | Framework/private utilities | Keep custom | These functions encode the versioned retrieval contract; private helpers would add drift. |
| Middleware | Custom subclasses of LangChain middleware | Native middleware hooks | Keep native extension | Budget, cancellation, safe events, and policy are application invariants already using supported hooks. |
| Human approval | Deterministic proposal/accept records | Framework HITL interrupts | Keep current boundary | Model-visible tools cannot commit canonical state; native HITL is needed only for future guarded side effects. |
| Checkpoints | Native Postgres checkpointer plus bounded local deterministic state | LangGraph checkpointers | Keep native provider path | Product and execution state remain separated. |
| Streaming | Native messages/updates stream plus safe collector | LangGraph streaming/callbacks | Keep narrow projection | Product events must suppress text/arguments and remain durable and replayable. |
| Observability | Langfuse adapter and durable events | LangSmith tracing support | Keep accepted Langfuse plane | Optional tracing does not replace product events or create a second canonical telemetry plane. |
| Evaluation datasets/runs | Versioned deterministic cases plus optional semantic grader | LangSmith evaluation APIs | Keep current local/release contract | LangSmith may be added for hosted experiment analysis, but cannot replace deterministic invariant assertions or become required product state. |
| Retries/fallbacks | Bounded settings plus provider adapters | Integration SDK retry behavior and middleware | Delegate transport retries; keep policy | Groundloom never silently falls back to a different provider or deterministic result after a configured provider fails. |
| Caching/rate limiting | Durable workspace budgets and run limits | Model caches and rate-limit middleware | Do not add globally | Cross-tenant caches risk scope leakage; caching requires a future keyed, provenance-aware product contract. Current budgets remain authoritative. |
| Async/batching | Durable workers, bounded embedding batches, specialist tasks | Runnable batch/async APIs | Use only at proven seams | Embedding batches already use the integration batch API. Durable work ownership, leases, retries, cancellation, and audit cannot be replaced by in-process runnable concurrency. |
| Deterministic local AI | Hash embeddings, overlap reranker, rubric grader, local runtime | Framework fakes | Keep deterministic implementations | They are transparent credential-free baselines, not provider-transport reimplementations. |
| OCR/source scanning | Explicit bounded HTTP sidecars outside `app/ai` | No LangChain model primitive | Keep purpose-built | These services process untrusted bytes before model use and have binary/verdict contracts, not chat-model contracts. |
| Outbox/webhooks | At-least-once HTTP delivery outside `app/ai` | No LangChain primitive | Keep purpose-built | Delivery leases, replay, signatures, and audit are application infrastructure. |
| Provider error contract | Stable Groundloom codes/messages | No product-aware framework equivalent | Keep small translator | Errors remain redacted, retry-aware, and independent of SDK exception text. |
| Prompt asset loading | Allowlisted package-resource loader | No equivalent Groundloom version policy | Keep custom | It enforces reviewed filenames and installed-package parity. |
| Runtime/service ports | Groundloom protocols and settings factory | No tenant-aware framework equivalent | Keep custom | These seams prevent runtime code from importing persistence or receiving tenant authority. |

## Dependency decision

The base runtime explicitly pins `langchain-core` because tool schemas and
documents are now base contracts. The optional `agent` extra pins the tested
`langchain`, `langsmith`, provider integrations, and `langchain-cohere`.
These packages and the Cohere SDK report MIT licenses. The Cohere integration
adds SDK/tokenizer transitive dependencies, so it remains optional and is
loaded only when the configured reranker is Cohere.

## Regression guards

- `test_ai_provider_adapters_do_not_reimplement_http_transport` prevents a new
  AI-local transport from quietly returning.
- `test_model_facing_tools_are_langchain_tools_with_bounded_pydantic_inputs`
  locks the explicit inventory and validates bounded schemas and citations.
- Provider tests inject LangChain-compatible fakes and assert stable product
  errors without coupling tests to private HTTP payloads.
- Skill-author tests prove one bounded structured call, malformed-output and
  outage behavior, generation provenance, and the separate publication gate.
- Deep Agents compilation, skills, subagent, middleware, checkpoint, stream,
  tenant, retrieval, and evaluation tests remain part of the gate.

## What deserved the roast

- The backend advertised an AI skill author whose only production-provider
  behavior was to return `503`. That was a button wired to a refusal, not a
  feature. It now performs one real bounded structured call and still cannot
  publish.
- Three provider adapters hand-built HTTP payloads, authorization headers,
  retry behavior, nested response indexing, and JSON parsing despite already
  depending on the LangChain ecosystem. That was maintenance cosplay. The
  dedicated integrations now own those details.
- Model-facing tools were anonymous nested closures. They worked only because
  the framework was generous about inference, while the documentation claimed
  typed tool contracts. They are now explicit `BaseTool` values with schemas.
- Tests asserted homemade provider wire shapes instead of Groundloom's actual
  integration boundary. They now inject narrow LangChain-compatible clients
  and test product validation/error semantics.
- The architecture document claimed the skill author was a Deep Agent even
  though the code never built one. The implementation and normative docs now
  agree: it is a direct structured call because an agent loop would be waste.
- `backend/app/services.py` remains an oversized ownership hotspot. This change
  removes AI-provider mechanics from it, but capability-by-capability service
  extraction remains the already-recorded P1 rather than being hidden inside a
  risky unrelated rewrite.

## Non-goals

This audit does not replace domain repositories with generic vector stores,
move canonical memory into a LangGraph store, add a rigid outer graph, expose
provider-native objects to product APIs, or change the accepted Langfuse
observability decision. Those would be architectural regressions, not
LangChain adoption.
