# Groundloom documentation index

This directory is the normative specification for the product. Codex must follow the hierarchy below and must not treat examples or framework references as product requirements.

## Authority order

1. Product requirements and non-functional requirements define intended behavior.
2. Architecture and security documents define system invariants and boundaries.
3. Accepted ADRs explain durable decisions and trade-offs.
4. Contracts define exact interfaces.
5. Component specifications define subsystem behavior.
6. Implementation plans define sequencing, not new behavior.
7. Validation documents define proof of compliance.
8. `ref/` is informative source material and never overrides Groundloom specifications.

If two normative documents conflict, stop and record the conflict in governance; resolve it before implementation.

## Requirement namespaces

| Prefix | Meaning |
|---|---|
| `FR-*` | Functional product requirement |
| `UI-*` | UI behavior or state requirement |
| `NFR-*` | Non-functional requirement/SLO |
| `ARCH-*` | Architecture invariant |
| `DATA-*` | Data invariant |
| `AGENT-*` | Primary-agent or harness behavior |
| `TOOL-*` | Tool contract |
| `API-*` | Public API contract |
| `EVT-*` | Event contract |
| `SEC-*` | Security requirement |
| `OPS-*` | Operational requirement |
| `TEST-*` | Validation case |

## Reading paths

### New implementer

`product/product-requirements.md` → `architecture/system-architecture.md` → `deepagents/primary-project-agent.md` → `contracts/agent-tool-contracts.md` → `implementation/master-roadmap.md`.

### Agent-runtime work

Read all `deepagents/` specifications plus the corresponding material in `ref/deepagents/`, then the applicable ADRs and trajectory evaluations.

### Product/API work

Read `product/`, `components/`, `contracts/`, data/security architecture, and the matching implementation phase.

### Release review

Read `validation/release-gates.md`, the traceability matrix, operations runbooks, open risks, and the phase exit report.

## Directory map

- `governance/`: interpretation, change, traceability, glossary, risks.
- `product/`: scope, UI behavior, journeys, lifecycle, roles, NFRs.
- `architecture/`: system-wide boundaries and deployment.
- `deepagents/`: Groundloom-specific harness specification.
- `components/`: subsystem contracts and definitions of done.
- `contracts/`: exact public/internal interfaces.
- `adrs/`: architectural decisions.
- `codex/`: execution and review protocol.
- `implementation/`: phased checklists and gates.
- `validation/`: tests, evaluations, security, reliability, release evidence.
- `operations/`: development and production runbooks.
- `ref/`: attached UI and verbatim Deep Agents reference material.
