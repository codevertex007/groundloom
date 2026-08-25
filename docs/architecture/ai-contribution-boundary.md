# AI contribution boundary

Groundloom separates AI engineering work from deterministic backend work while
keeping one integrated product contract.

## Ownership map

| Area | AI engineering owns | Backend/product engineering owns |
|---|---|---|
| Agent runtime | `backend/app/ai/runtime/`, `middleware/`, `state/`, provider harness wiring, stream projection | Authorization context, service contracts, persistence, jobs, approvals, canonical writes |
| Prompt assets | `backend/app/ai/prompts/*.txt`, reviewed and versioned with the runtime | Prompt version provenance and release/configuration validation |
| Retrieval/evaluation | `backend/app/ai/providers/embeddings.py`, `reranking.py`, `evaluation.py` and their provider tests | Source scope, citation lineage, derived-index lifecycle, deterministic validation invariants |
| AI frontend | `frontend/src/ai/` focused agent/activity and AI skill-author components | Screen composition, API transport, canonical state and permissions |

There are no flat AI compatibility modules in `app/`. Backend services import
the explicit AI contracts under `app.ai`; deterministic product services remain
outside that package and must not duplicate provider behavior.

## Prompt contract

System prompts are UTF-8 `.txt` package assets. `app.ai.prompt_loader.load_prompt`
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
