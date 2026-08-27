# ADR-035: LangChain-native provider and tool interfaces

- Status: Accepted
- Date: 2026-08-27
- Deciders: Groundloom engineering

## Context

The primary runtime already used Deep Agents, LangGraph checkpoints, and
LangChain middleware, but three narrower AI capabilities bypassed the same
ecosystem. Embeddings, Cohere reranking, and semantic evaluation manually
constructed HTTP requests and decoded provider responses. The AI skill-author
endpoint rejected every configured provider instead of using the existing
model profile. Model-facing tools were plain closures without explicit
LangChain `BaseTool` identity or bounded Pydantic argument schemas.

That code duplicated provider SDK behavior for authentication, endpoints,
retries, response parsing, structured output, and future API changes. It also
made the tool contract weaker than the normative typed-tool requirement.

## Decision

Use the pinned dedicated LangChain integrations at generic provider seams:

- `OpenAIEmbeddings.embed_documents` for OpenAI-compatible embeddings;
- `ChatOpenAI` composed with `ChatPromptTemplate` and typed structured
  output for the bounded semantic grader;
- provider-neutral `init_chat_model`, `ChatPromptTemplate`, and typed
  structured output for one bounded draft-only skill-author call;
- `CohereRerank` with the Cohere v2 SDK client for optional reranking; and
- LangChain `@tool` and `BaseTool` plus Pydantic `args_schema` for every
  Groundloom model-facing tool.

Delete the AI-local generic HTTP client. Provider integrations own transport,
authentication, endpoint serialization, and their supported retry behavior.
Groundloom retains a small status-based exception translator so SDK failures
still become redacted stable product errors. It also retains finite/dimension
vector checks, rerank completeness/order checks, and Pydantic semantic/skill
result validation before data reaches product state. Skill authoring remains a
single model call rather than a Deep Agent because it has one bounded result,
no tools, and no adaptive loop; validation and publication remain separate
deterministic domain commands.

Do not replace the tenant-scoped retrieval repository, RLS-aware pgvector
projection, immutable citation lineage, approved memory store, skill backend,
policy middleware, durable public-event projection, or product proposal/commit
boundary with generic framework storage. Those are Groundloom invariants rather
than generic model plumbing.

## Dependencies and maintenance

Pin the tested LangChain, core, LangSmith, and provider-package versions in the
`agent` extra; pin `langchain-core` in the base runtime because tools and
documents are base contracts. Add `langchain-cohere==0.6.0`, which brings the
Cohere SDK/tokenizer stack and remains lazy and optional. The added direct
packages and reported transitive Cohere SDK are MIT licensed. Upgrades require
provider contract tests, typed-tool schema tests, the pinned Deep Agents
compilation probe, and retrieval/evaluation regression gates.

## Consequences

Provider API changes are absorbed by supported integration packages instead of
three local payload parsers. Tool descriptions and validation become visible to
LangChain, Deep Agents profiles, models, and tests. The Cohere configuration is
an API root for the v2 client, defaulting to `https://api.cohere.com`, not a
manual v1 rerank endpoint. Product errors and security boundaries remain stable.

## Validation

`backend/tests/test_retrieval_adapters.py`, `test_reranking.py`, and
`test_evaluation.py` and `test_skill_author.py` exercise integration-facing
interfaces and malformed or unavailable provider behavior. The skill endpoint
test also proves model output remains an unpublished draft with pinned
generation provenance. `test_ai_boundary.py` forbids hand-written HTTP
inside the AI package and proves the exact tool inventory consists of LangChain
`BaseTool` values with bounded Pydantic inputs. The full Deep Agents,
retrieval, tenant, docs, Ruff, mypy, and backend gates remain required.
