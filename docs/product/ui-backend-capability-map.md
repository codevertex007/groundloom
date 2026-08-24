# UI-to-backend capability map

| UI action | Command/query | Agent involvement | Durable result | Event family |
|---|---|---|---|---|
| Create project | `POST /v1/projects` | Start primary thread after commit | Project/config version | `project.*`, `run.*` |
| Upload source | Upload session + finalize | None | Source/source version/job | `source.*` |
| Ask collaborator | Thread message command | Primary project agent | Run/messages/events | `run.*`, `todo.*`, `tool.*` |
| Approve outline | Proposal approval command | Resume same agent thread | Outline version/approval | `approval.*`, `outline.*` |
| Search source | Retrieval query/tool | Optional | Audit/trace only | `retrieval.*` internal |
| Generate/revise content | Agent tool calls | Primary + optional subagents | Draft patch/validation | `patch.*`, `validation.*` |
| Accept/reject patch | Deterministic command | None | Content version or decision | `patch.accepted/rejected` |
| Create skill with AI | Skill-author thread | Dedicated agent | Draft skill version | `skill.*` |
| Publish skill | Deterministic approval/command | None | Published skill version | `skill.published` |
| Start export | Export command | Approval discussion optional | Export job/artifact | `export.*` |

## Concrete route map delivered by the reference-aligned client

| Client surface | Real API calls |
|---|---|
| Projects grid | `GET /v1/projects`, `POST /v1/projects` |
| Sources library/upload | `GET /v1/sources`, `POST /v1/sources/uploads`, `GET /v1/source-versions/{id}/passages/{passage_id}` |
| Skills registry | `GET /v1/skills`, `POST /v1/skills`, `POST /v1/skill-versions/{id}/validate`, `POST /v1/skill-versions/{id}/publish` |
| Canvas | `GET /v1/projects/{id}`, `/outline`, `/content`, `/patches`, `/threads/{thread_id}/events` |
| Copilot | `POST /v1/projects/{id}/threads/messages`, `POST /v1/runs/{id}/cancel`, `POST /v1/runs/{id}/resume` |
| Evidence search | `GET /v1/projects/{id}/sources/search?q=...` |
| Diff review | `POST /v1/patches/{id}/accept`, `POST /v1/patches/{id}/reject` |
| Export | `POST /v1/exports`, `GET /v1/exports/{id}`, scoped download URL |

The frontend consumes stable DTOs and normalized events. It never reads LangGraph checkpoint schemas, raw model messages, or database tables directly.
