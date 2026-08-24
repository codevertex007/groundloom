# Codex build protocol

For each vertical slice, Codex must: identify requirement IDs; read references/specs; inspect repository; propose a bounded plan; define/update contracts; implement migrations/domain/service/API/runtime/UI as applicable; write tests; add telemetry; update docs/traceability/checklists; run gates; and produce a handoff.

Do not implement multiple phases speculatively. Establish executable foundations, then the thinnest end-to-end path, then expand. When blocked by an undecided `OQ-*`, stop if the default would materially constrain the product; otherwise use the recorded default and document it.

Implementation evidence includes commands/tests and outcomes, not claims. Preserve unrelated changes. Never hide a failing gate by weakening assertions, skipping tests, swallowing errors, or adding silent fallback behavior.
