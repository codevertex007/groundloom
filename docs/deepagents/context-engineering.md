# Context engineering

## Context layers, in order

1. Stable system/harness policy and tool instructions.
2. Trusted organization policy and scoped stable memory.
3. Skill metadata; full `SKILL.md` only when chosen.
4. Compact project snapshot with immutable IDs/versions.
5. Active UI selection and immediate user request.
6. Bounded evidence/tool results.
7. Recent messages plus structured summary of older history.

Do not inject all sources, all blocks, all skills, complete workspace metadata, or raw historical tool outputs each turn.

## Manifests and retrieval

Expose authorized source/skill manifests with IDs, names, versions, types, status, size, and short description. The agent selects items then uses read/search tools. Tools enforce scope and return bounded typed results with continuation handles when necessary.

## Compaction/offload

Large results move to thread-scoped filesystem/backend storage with a compact manifest. Summaries preserve decisions, unresolved questions, accepted/rejected proposals, pinned versions, and next tasks; they are execution aids, not canonical history. Preserve complete assistant tool-call/tool-result pairing.

## Budgets

Configure maximum context, evidence passages, tool result bytes, concurrent subagents, repair iterations, and run cost/time. On a limit, present a useful partial result and resume choice rather than silently dropping critical constraints.
