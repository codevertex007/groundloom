# Agent tool contracts

Initial tool registry:

| ID/name | Mode | Output/side effect |
|---|---|---|
| `TOOL-PROJ-001 get_project_snapshot` | Read | Compact pinned project view |
| `TOOL-PROJ-002 get_active_selection` | Read | Active module/block/UI context |
| `TOOL-PLAN-001 write_project_todos` | Execution | Checkpoint/public todo state |
| `TOOL-RET-001 search_source_passages` | Read | Bounded `EvidenceBundle` |
| `TOOL-RET-002 read_source_passage` | Read | Authorized immutable passage/neighbors |
| `TOOL-CONT-001 read_content_blocks` | Read | Versioned typed blocks |
| `TOOL-CONT-002 propose_outline` | Proposal | Durable reviewable outline proposal |
| `TOOL-CONT-003 propose_block_patch` | Proposal | Validated non-canonical patch |
| `TOOL-VAL-001 submit_draft_for_validation` | Check | Validation execution/findings |
| `TOOL-VAL-002 request_quality_check` | Check | Bounded semantic review |
| `TOOL-EXP-001 start_export` | Job request | Authorized/approval-gated export job |

Each implementation defines Pydantic input/output, runtime-context scope, maximum result, timeout/retry, errors, idempotency, event/trace metadata, and approval behavior. Commit actions `accept_patch`, `publish_skill`, and direct artifact publication are deliberately not available to the primary agent.
