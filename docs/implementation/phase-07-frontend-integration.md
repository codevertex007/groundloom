# Phase 07 — Complete frontend integration

## Checklist

- [x] `IMPL-07-001` Extract screen/route/component inventory from attached UI and map to contracts.
- [x] `IMPL-07-002` Shared JSDoc-typed API client and explicit local auth/workspace headers; production identity integration remains deployment work.
- [x] `IMPL-07-003` Projects/New Project/Sources/Skills screens and core states, including bounded cursor pagination/load-more, active published-skill selection, scope filters/forking, and immutable source-version history/revision upload.
- [x] `IMPL-07-004` Canvas outline/content/source explorer with block selection and citations.
- [x] `IMPL-07-005` Primary-agent panel with replay-safe events, todos, subagents, approvals, and connected cancel/resume controls.
- [x] `IMPL-07-006` Diff/review/accept/reject/conflict flows.
- [x] `IMPL-07-007` Export/preview/settings/command palette.
- [x] `IMPL-07-008` Accessibility-oriented keyboard, responsive, reconnect/error/empty states; the shared client reconnects finite SSE replay with `Last-Event-ID` and exposes connection state, while `ErrorNotice` renders typed retry/permission/terminal failures in-app without native browser alerts.
- [x] `IMPL-07-008a` Native frontend API-client contract tests cover typed retryable errors, correlation headers, finite SSE parsing, reconnect cursor propagation, deduplication input, and offline cancellation; a static UI contract test covers reference surfaces, connected mutation endpoints, dialogs, and keyboard semantics.
- [x] `IMPL-07-009a` Playwright local E2E covers project creation, persistent-agent drafting, proposal acceptance, settings persistence, command-palette navigation, and real backend/frontend startup; visual baselines remain a separate environment-specific gate.
- [x] `IMPL-07-009b` Server-rendered component tests cover shared headers, empty states, and command-palette route inventory with the actual React components.
- [x] `IMPL-07-009c` Playwright covers source upload/readiness, project evidence selection, source-grounded drafting, and citation-panel navigation.
- [x] `IMPL-07-009` Component, stable visual-regression, and full e2e suite; 3 component tests, 10 Playwright tests (9 semantic journeys plus the pinned visual-baseline test), committed Windows Chromium empty-state baselines, semantic needs-revision coverage for source-less drafts, and serious/critical axe assertions pass. Non-Windows CI runs the semantic suite and skips the pinned pixel lane.
- [x] `IMPL-07-010` Reference-aligned studio shell, New Project composition, and narrow viewport hardening; the sidebar/brand hierarchy now follows the supplied dark studio reference, Groundloom and Knowledge Studio remain a compact stacked wordmark, Projects/Sources use the reference inline header and centered content frame, project filters use the reference pill row, empty states use the reference dashed panel, project cards expose the reference type/status/progress metadata, and New Project uses the reference fixed header, dark content controls, content-type cards, dashed evidence area, selection lists, and footer. Mobile layouts collapse the rail and wrap controls without horizontal overflow. The static UI contract suite protects the branding, modal composition, and responsive CSS invariants.

## Exit gate
The reference surfaces are implemented against the real local backend. API-client reconnect/error automation, a static UI contract suite that rejects native `alert()` regressions and protects the reference shell/responsive invariants, actual React component rendering tests, cursor-paginated project loading, and 10 Playwright tests covering project creation with active skill selection, approval resume, proposal accept/reject, deterministic plus semantic review states (including citation-required source-less drafts), skills scope filtering/forking/author/repair/publish, settings, command palette, dropped-stream reconnect, permission-denied rendering, source version history/revision upload, exact source citations, visual stable states, and rendered serious/critical axe checks pass locally. ADR-023 records the pinned Windows visual lane and cross-platform semantic policy.
