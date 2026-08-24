# Phase 07 — Complete frontend integration

## Checklist

- [x] `IMPL-07-001` Extract screen/route/component inventory from attached UI and map to contracts.
- [x] `IMPL-07-002` Shared JSDoc-typed API client and explicit local auth/workspace headers; production identity integration remains deployment work.
- [x] `IMPL-07-003` Projects/New Project/Sources/Skills screens and core states.
- [x] `IMPL-07-004` Canvas outline/content/source explorer with block selection and citations.
- [x] `IMPL-07-005` Primary-agent panel with replay-safe events, todos, subagents, approvals, and connected cancel/resume controls.
- [x] `IMPL-07-006` Diff/review/accept/reject/conflict flows.
- [x] `IMPL-07-007` Export/preview/settings/command palette.
- [x] `IMPL-07-008` Accessibility-oriented keyboard, responsive, reconnect/error/empty states; the shared client reconnects finite SSE replay with `Last-Event-ID` and exposes connection state.
- [x] `IMPL-07-008a` Native frontend API-client contract tests cover typed retryable errors, correlation headers, finite SSE parsing, reconnect cursor propagation, deduplication input, and offline cancellation; a static UI contract test covers reference surfaces, connected mutation endpoints, dialogs, and keyboard semantics.
- [x] `IMPL-07-009a` Playwright local E2E covers project creation, persistent-agent drafting, proposal acceptance, settings persistence, command-palette navigation, and real backend/frontend startup; visual baselines remain a separate environment-specific gate.
- [x] `IMPL-07-009b` Server-rendered component tests cover shared headers, empty states, and command-palette route inventory with the actual React components.
- [x] `IMPL-07-009c` Playwright covers source upload/readiness, project evidence selection, source-grounded drafting, and citation-panel navigation.
- [ ] `IMPL-07-009` Component, visual-regression where stable, and full e2e suite; automated component rendering and committed visual baselines remain release evidence.

## Exit gate
The reference surfaces are implemented against the real local backend. API-client reconnect/error automation, a static UI contract suite, actual React component rendering tests, a Playwright E2E suite, and rendered serious/critical axe checks are local; committed visual baselines and the complete release journey matrix remain evidence work. ADR-023 records the browser-test dependency and baseline policy.
