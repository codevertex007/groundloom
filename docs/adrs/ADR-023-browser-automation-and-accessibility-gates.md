# ADR-023: Pinned browser automation and rendered accessibility gates

**Status:** Accepted  
**Date:** 2026-08-25

## Context

The reference UI cannot be proven by API-client tests or source inspection
alone. The critical project journey, rendered semantics, keyboard behavior, and
real backend/frontend wiring need a browser-runner that is reproducible in local
development and CI. Environment-specific screenshot baselines are not suitable
as a substitute for deterministic assertions without an agreed rendering
matrix.

## Decision

Use pinned `@playwright/test` for local and CI browser E2E, with an isolated
SQLite/filesystem backend started by `frontend/playwright.config.js`. Use the
pinned `@axe-core/playwright` integration for serious/critical rendered
accessibility violations. Keep visual screenshot baselines as a separate,
reviewed release artifact; do not commit machine-specific snapshots as product
truth.

## Consequences

Browser tests download a managed Chromium build and are slower than unit tests.
The isolated adapter makes the suite credential-free and prevents local test
data from becoming product state. Accessibility catches real contrast and
semantic regressions, while visual fidelity still requires a stable approved
rendering environment before release.

Both packages are development-only test dependencies and are not part of the
production bundle. Their versions are pinned through `frontend/package-lock.json`.

## Validation

`frontend/e2e/groundloom.spec.js` covers the create → collaborator → proposal →
accept journey, settings persistence, command-palette navigation, and an axe
serious/critical scan. CI installs Chromium and runs `npm run test:e2e`.
