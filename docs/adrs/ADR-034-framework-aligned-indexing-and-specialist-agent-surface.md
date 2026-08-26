# ADR-034: Framework-aligned indexing and explicit specialist agent surface

- Status: Accepted
- Date: 2026-08-27
- Deciders: Groundloom engineering

## Context

Source ingestion and index rebuild duplicated custom paragraph-to-vector logic.
Each normalized block produced one chunk whose text was truncated for
embedding, so a long block was not fully represented. Retrieval then collapsed
multiple chunk rows to one vector and loaded the complete selected corpus even
when PostgreSQL had already returned bounded pgvector candidates.

Deep Agents also adds a general-purpose subagent unless its harness profile
disables it. Groundloom's normative inventory defines three reviewed
specialists with narrower tool sets, so relying on the implicit delegate made
the executable surface broader than the documented surface.

## Decision

Use the pinned `langchain-text-splitters` package and
`RecursiveCharacterTextSplitter` for generic bounded text splitting. Keep
source parsing, authorization, lineage, chunk persistence, embeddings, vector
storage, and retrieval ranking in Groundloom-owned adapters because those are
product and security concerns.

Use one `replace_source_version_index` application integration for initial
ingestion and rebuild. Batch embedding requests, persist every chunk, and let
retrieval aggregate semantic similarity at the immutable source-block level.
For PostgreSQL, load the union of bounded pgvector and lexical candidates plus
their immediate neighbors; retain full selected-corpus scanning only for the
explicit local SQLite adapter.

Disable Deep Agents' implicit general-purpose subagent through the provider
`HarnessProfile`. Continue to compose only the three named Groundloom
specialists. Keep native Deep Agents middleware, skills, subagent isolation,
streaming, and LangGraph checkpointing rather than recreating them.

## Consequences

- Long normalized blocks receive complete derived semantic coverage.
- Ingestion and rebuild cannot silently use different chunk algorithms.
- Production retrieval work is bounded before materializing block/chunk data.
- A new MIT-licensed LangChain ecosystem dependency is pinned and becomes part
  of the base ingestion runtime.
- Chunk-size/overlap/batch settings enter the effective configuration
  fingerprint and must be pinned with derived-index provenance in a future
  processor-version migration.
- The actual subagent surface now matches the reviewed documentation.

## Validation

`test_index_rebuild_is_durable_idempotent_and_scoped` proves multi-chunk bounds
and rebuild equivalence. Retrieval/vector tests cover deterministic and
pgvector paths. Pinned Deep Agents provider tests capture the harness profile,
compile the graph, and exercise real specialist delegation with shared policy
and budget middleware.
