# Phase 07 — Complete frontend integration

## Checklist

- [x] `IMPL-07-001` Extract screen/route/component inventory from attached UI and map to contracts.
- [x] `IMPL-07-002` Shared JSDoc-typed API client and explicit local auth/workspace headers; production identity integration remains deployment work.
- [x] `IMPL-07-003` Projects/New Project/Sources/Skills screens and core states.
- [x] `IMPL-07-004` Canvas outline/content/source explorer with block selection and citations.
- [x] `IMPL-07-005` Primary-agent panel with replay-safe events, todos, subagents, approvals, cancel/resume controls.
- [x] `IMPL-07-006` Diff/review/accept/reject/conflict flows.
- [x] `IMPL-07-007` Export/preview/settings/command palette.
- [x] `IMPL-07-008` Accessibility-oriented keyboard, responsive, reconnect/error/empty states; the shared client reconnects finite SSE replay with `Last-Event-ID` and exposes connection state.
- [x] `IMPL-07-008a` Native frontend API-client contract tests cover typed retryable errors, correlation headers, finite SSE parsing, reconnect cursor propagation, deduplication input, and offline cancellation; a static UI contract test covers reference surfaces, connected mutation endpoints, dialogs, and keyboard semantics.
- [ ] `IMPL-07-009` Component, visual-regression where stable, and full e2e suite; browser smoke and static UI contract evidence are local, while automated browser rendering remains a release gate.

## Exit gate
The reference surfaces are implemented against the real local backend and the critical create/generate/review/accept journey passed browser smoke. API-client reconnect/error automation and a static UI contract suite are local; automated component rendering, accessibility, visual regression, and full browser e2e remain release evidence work.
