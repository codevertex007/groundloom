# Preferences and settings component

Owns typed user/workspace defaults such as locale, concise/detailed style, project defaults, review policy, export defaults, retention references, and allowed model profiles. Settings are versioned/audited when they affect reproducibility or policy.

Runtime context receives only relevant resolved values. Stable approved preferences may also project to memory, but settings remain canonical. Precedence: organization policy → workspace policy/default → user preference → project configuration → explicit current request, with policy constraints always winning.

Tests cover precedence, invalid configuration, role checks, run pinning, change during active run, memory divergence, audit, and secret exclusion.
