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
- [x] `IMPL-07-009` Component, stable visual-regression, and full e2e suite; 3 component tests, 10 Playwright tests (9 semantic journeys plus the pinned visual-baseline test), committed Windows Chromium empty-state baselines, and serious/critical axe assertions pass. Non-Windows CI runs the semantic suite and skips the pinned pixel lane.

## Exit gate
The reference surfaces are implemented against the real local backend. API-client reconnect/error automation, a static UI contract suite, actual React component rendering tests, 10 Playwright tests covering project creation, approval resume, proposal accept/reject, skills author/repair/publish, settings, command palette, dropped-stream reconnect, permission-denied rendering, sources/citations, visual stable states, and rendered serious/critical axe checks pass locally. ADR-023 records the pinned Windows visual lane and cross-platform semantic policy.
