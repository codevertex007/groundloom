# State and persistence

| State | Authority | Examples |
|---|---|---|
| Product/domain | Postgres | projects, versions, blocks, citations, proposals, approvals, jobs |
| Agent execution | Postgres checkpointer through the worker database connection | messages, tool bookkeeping, todos, summaries, interrupts |
| Binary/artifact | Object storage | uploads, normalized documents, previews, exports |
| Scratch | Deep Agents backends | notes, offloaded tool results, temporary drafts |
| Derived | pgvector/search/cache | chunks, embeddings, rankings, projections |
| Telemetry | Langfuse | traces, spans, feedback, evaluation observations |

**ARCH-STATE-001:** A product screen must be reconstructable without interpreting agent messages.  
**ARCH-STATE-002:** Scratch/checkpoint files are not canonical source/content storage.  
**ARCH-STATE-003:** Derived data may be rebuilt from canonical versioned inputs.  
**ARCH-STATE-004:** Agent proposals and deterministic commits are separate durable actions.  

Domain mutation + outbox commit atomically, then the tool returns the durable record ID and the runtime checkpoints. Replay resolves the same idempotency key to the existing record.
