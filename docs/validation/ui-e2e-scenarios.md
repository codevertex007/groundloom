# UI end-to-end scenarios

- `TEST-E2E-001`: create project → clarify → approve plan → stream modules → reload/resume → citation. Covered by `groundloom.spec.js` project and approval tests.
- `TEST-E2E-002`: targeted simplification → diff → reject → canonical unchanged.
- `TEST-E2E-003`: evidence-backed patch → accept → exactly one new version; stale concurrent accept conflicts.
- `TEST-E2E-004`: upload/retry/version source → old run remains pinned; new run opts into revision. The browser suite covers immutable version history and revision upload.
- `TEST-E2E-005`: AI skill draft → validation → repair → authorized workspace publication. Covered by the skill lifecycle browser test and backend immutable-repair test.
- `TEST-E2E-006`: validation → export approval → worker retry → one artifact/download.
- `TEST-E2E-007`: disconnect/reconnect event replay without duplicate activity. Covered by the dropped-stream browser test and native SSE cursor test.
- `TEST-E2E-008`: revoked permission during run/approval/download denies safely.
- `TEST-E2E-009`: keyboard/screen-reader critical journey. Covered by command-palette keyboard navigation and the axe serious/critical scan.

Use stable model fakes for deterministic CI and a smaller live-model staging suite for trajectory quality.
