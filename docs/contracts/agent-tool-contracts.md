# Agent tool contracts

Initial tool registry:

| ID/name | Mode | Output/side effect |
|---|---|---|
| `TOOL-PROJ-001 get_project_snapshot` | Read | Compact pinned project view |
| `TOOL-PROJ-002 list_project_skills` | Read | Metadata for skill versions selected by this project |
| `TOOL-RET-001 search_source_passages` | Read | Bounded `EvidenceBundle` |
| `TOOL-RET-002 read_source_passage` | Read | Authorized immutable passage/neighbors |
| `TOOL-CONT-001 read_current_content` | Read | Versioned typed blocks |
| `TOOL-CONT-002 validate_current_content` | Read | Deterministic validation findings without canonical mutation |
| `TOOL-CONT-003 propose_text_patch` | Proposal | Validated non-canonical patch; operations are limited to the supported typed block payload contracts |
| `TOOL-MEM-001 read_workspace_memory` | Read | Approved user-scoped memory |

Each implementation defines Pydantic input/output, runtime-context scope, maximum result, timeout/retry, errors, idempotency, event/trace metadata, and approval behavior. Commit actions `accept_patch`, `publish_skill`, and direct artifact publication are deliberately not available to the primary agent.
