# UI end-to-end scenarios

- `TEST-E2E-001`: create project → clarify → edit/approve plan → stream modules → reload/resume → citation.
- `TEST-E2E-002`: targeted simplification → diff → reject → canonical unchanged.
- `TEST-E2E-003`: evidence-backed patch → accept → exactly one new version; stale concurrent accept conflicts.
- `TEST-E2E-004`: upload/retry/version source → old run remains pinned; new run opts into revision.
- `TEST-E2E-005`: AI skill draft → validation failure → repair → authorized workspace/org publication.
- `TEST-E2E-006`: validation → export approval → worker retry → one artifact/download.
- `TEST-E2E-007`: disconnect/reconnect event replay without duplicate activity.
- `TEST-E2E-008`: revoked permission during run/approval/download denies safely.
- `TEST-E2E-009`: keyboard/screen-reader critical journey.

Use stable model fakes for deterministic CI and a smaller live-model staging suite for trajectory quality.
