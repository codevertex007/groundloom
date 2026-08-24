# Dependency map

```text
00 foundations
  → 01 identity/domain/persistence
      → 02 sources/retrieval
      → 03 agent foundation
          → 04 skills/memory/subagents
          → 05 content/proposals
              → 06 quality/export
                  → 07 full UI
                      → 08 hardening
                          → 09 release
```

Thin UI shells may start earlier against generated clients/fakes, but acceptance waits for real contracts. Quality datasets/fixtures start with phases 02–05 and mature in 06. Security, observability, docs, and tests are continuous work, not deferred phase-08 features; phase 08 verifies completeness under adversarial/load/failure conditions.
