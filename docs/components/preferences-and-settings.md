# Preferences and settings component

Owns typed user/workspace defaults such as locale, concise/detailed style, project defaults, review policy, export defaults, retention references, and allowed model profiles. Settings are versioned/audited when they affect reproducibility or policy.

Runtime context receives only relevant resolved values. Stable approved preferences may also project to memory, but settings remain canonical. Precedence: organization policy → workspace policy/default → user preference → project configuration → explicit current request, with policy constraints always winning.

Tests cover precedence, invalid configuration, role checks, run pinning, change during active run, memory divergence, audit, and secret exclusion.

The local implementation persists the typed workspace preference projection in
`workspace_preferences` and exposes `GET/PUT /v1/workspace/preferences`. The
preferences include review-before-apply, citation requirement, default export,
and plan-approval policy. Updates increment `version_no`, emit an audit/outbox
record, accept an idempotency key, and are folded into each new project's
pinned configuration. Existing project pins are not rewritten by later setting
changes.
