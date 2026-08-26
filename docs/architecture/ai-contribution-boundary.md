# AI contribution boundary

Groundloom separates AI engineering work from deterministic backend work while
keeping one integrated product contract.

## Ownership map

| Area | AI engineering owns | Backend/product engineering owns |
|---|---|---|
| Reusable harness | `packages/groundloom-agent-harness/`: budgets, policy middleware, cancellation, safe events/streaming, read-only skill backend | No Groundloom imports or product authority |
| Agent composition | `backend/app/ai/agent.py`, `middleware/`, `runtime/`, `persistence/`, tools and subagents | Authorized `backend/app/integrations/ai/` implementations, jobs, approvals, canonical writes |
| Prompt assets | `backend/app/ai/prompts/*.txt`, reviewed and versioned with the runtime | Prompt version provenance and release/configuration validation |
| Retrieval/evaluation | `backend/app/ai/retrieval/`, `evaluation/`, and `common/provider_http.py` | Source scope and SQL repository in `backend/app/integrations/ai/`; citation lineage, derived-index lifecycle, deterministic validation invariants |
| Deterministic ingestion/export infrastructure | No model authority; the pinned LangChain splitter is consumed only through the document adapter | `backend/app/integrations/documents/`, `integrations/exports/`, and `integrations/ai/indexing.py` own parsing, derived-index persistence, and binary rendering |
| AI frontend | `frontend/src/ai/` focused agent/activity and AI skill-author components | Screen composition, API transport, canonical state and permissions |

There are no flat AI compatibility modules or obsolete import shims in `app/`.
Model-facing tools use `AgentServicePort` and never import the product service
module. The backend adapter binds trusted workspace/project context and is the
only bridge to persistence. `agent.py` is the only Deep Agents composition root.

Selected immutable skill versions are exposed to Deep Agents through a bounded
read-only `/skills/project/` backend. `read_file` and `ls` are retained for this
purpose; filesystem writes, edits, deletion, search outside the projection, and
execution are unavailable.

## Prompt contract

System prompts and subagent description text are UTF-8 `.txt` package assets.
`app.ai.prompt_loader.load_prompt`
allows only registered exact filenames, rejects empty assets, and loads them
through `importlib.resources` so source-tree and installed-package behavior
match. Prompt assets are included in the Python package data and their runtime
version remains `groundloom.prompt.v1` until a deliberate prompt contract
change is reviewed. Provider request payloads may still contain bounded runtime
data, but prompt instructions are never hidden in orchestration code.

## Contribution rules

AI contributors may change provider adapters, prompt text, harness descriptions,
and AI-specific UI components with focused tests. Backend contributors may
change canonical services, migrations, authorization, workers, and API/event
contracts. A change crossing the boundary must update the relevant contract,
traceability row, security tests, and this ownership map in one change.

Neither side may grant the model unrestricted SQL, shell, filesystem, network,
credentials, object storage, or tenant scope. Agent-generated changes remain
reviewable proposals until deterministic application commands accept them.
The cross-cutting deterministic audit, event/outbox, idempotency, operational,
and local-checkpoint services live under `backend/app/application/`; model-facing
code does not import those modules directly.
