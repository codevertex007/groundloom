# Requirements-to-test matrix

This is the initial planned matrix. Codex must replace planned identifiers with concrete test paths/names and evidence as implementation progresses.

| Requirements | Planned proof |
|---|---|
| `FR-PROJECT-001..003` | `backend/tests/test_api_vertical_slice.py::test_project_source_grounded_run_and_replay`; browser smoke create/reload/canvas |
| `FR-SOURCE-001..003` | `backend/tests/test_api_vertical_slice.py::test_project_source_grounded_run_and_replay`, `::test_source_revision_is_immutable_and_keeps_lineage`; scoped retrieval service, passage lineage, and immutable revision API |
| `FR-SKILL-001..002` | `backend/tests/test_api_vertical_slice.py::test_skill_publish_validation_and_export`; draft/validate/publish role path |
| `FR-AGENT-001..002` | `backend/tests/test_api_vertical_slice.py::test_project_source_grounded_run_and_replay`; durable adaptive local trajectory events |
| `FR-CONTENT-001..005` | `backend/tests/test_api_vertical_slice.py::test_patch_reject_and_accept_exactly_once`; immutable content version and exact-once decision |
| `FR-QUALITY-001` | `backend/app/services.py::validate_content`; `/v1/projects/{id}/validate` contract |
| `FR-EXPORT-001` | `backend/tests/test_api_vertical_slice.py::test_skill_publish_validation_and_export`; deterministic PDF bytes and scoped download |
| `FR-AUDIT-001` | `backend/app/services.py::audit`; provenance on run/content/export mutations |
| `UI-STATE-001..002` | Browser smoke of project empty/loading/canvas states; React API error banner and reload-backed state |
| `UI-RUN-001..002` | Browser smoke durable activity panel; `/v1/threads/{id}/events` replay DTO and `/events/stream` SSE smoke |
| `UI-PATCH-001..002` | Browser smoke proposal review; `test_patch_reject_and_accept_exactly_once` |
| `UI-CITE-001`, `UI-A11Y-001` | Canvas citation panel and keyboard `Ctrl/Cmd+K`, `Ctrl/Cmd+Enter`; browser DOM/screenshot evidence |
| `NFR-REL-001..004` | durability, replay, failure injection, backup/restore |
| `NFR-PERF-001..004` | API/retrieval/agent-activity load scenarios |
| `SEC-AUTH-001..006` | route/service/repository/tool cross-tenant matrix |
| `ARCH-STATE-001..004` | architecture/static tests plus recovery/proposal tests |
| `TOOL-*` | per-tool schema/auth/replay/bounds/trace tests |
| `API-*`, `EVT-*` | OpenAPI/SSE schema, compatibility, replay tests, and `test_project_source_grounded_run_and_replay` stream assertion |

Release blocks on any active requirement without proof or explicitly approved manual verification.
