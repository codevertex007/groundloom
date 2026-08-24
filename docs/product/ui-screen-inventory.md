# UI screen inventory

The attached `docs/ref/ui/design_ref.zip` is the visual baseline. During frontend implementation, produce a route/component inventory from the archive and preserve the states below.

| Surface | Required states and behavior |
|---|---|
| Projects | Loading, empty, populated, filtered, pagination, error; status and latest durable progress |
| New Project | Type, brief, sources, active skills, validation, create, agent-start/retry |
| Sources | Upload, scan/parse/index progress, ready, failed, version history, replace/new version |
| Source explorer | Search, page/section navigation, passage highlight, citation back-navigation |
| Skills | Starter/org/workspace filters, package detail, version history, fork, draft, validate, publish |
| AI skill author | Conversation, draft preview, validation errors, repair, approval/publication |
| Project canvas | Persistent agent panel, outline/content tabs, active module/block, citations, run activity |
| Outline | Proposed/approved versions, module statuses, edit/reorder, approval/rejection |
| Content | Typed block rendering, selection, citation markers, proposed additions/deletions/changes |
| Review | Deterministic checklist, semantic evaluation, evidence, override with reason |
| Export/preview | Version/template selection, approval if configured, job status, artifact download |
| Settings | User/workspace preferences, render defaults, model/policy visibility by role |
| Command palette | Navigation and deterministic commands; unavailable commands explain why |

## UI invariants

- **UI-STATE-001:** Reload MUST reconstruct state from durable APIs/events, not local optimistic memory alone.
- **UI-STATE-002:** Loading, empty, unavailable, permission-denied, retryable error, and terminal error MUST be distinct.
- **UI-RUN-001:** Activity MUST identify todos, tools, subagents, approvals, and jobs without revealing hidden reasoning.
- **UI-RUN-002:** Replayed events MUST not duplicate visible items.
- **UI-PATCH-001:** Proposed and canonical content MUST be visually distinct.
- **UI-PATCH-002:** Accept/Reject MUST show target version and report conflicts.
- **UI-CITE-001:** Citation activation MUST open the exact stored passage context where available.
- **UI-A11Y-001:** All critical actions and status changes MUST be keyboard accessible and screen-reader announced.

## Extracted reference inventory (design_ref.zip)

The archive contains one Design Canvas export, `Knowledge Platform.dc.html`, with the following implemented reference regions and interactions. The extracted directory is temporary and is not shipped as application code.

| Route/surface | Reference behavior observed | Groundloom implementation |
|---|---|---|
| `/projects` | Warm neutral workspace shell, collapsible left navigation, search/filter toolbar, cards with source/section counts and progress, empty state, New Project action | `ProjectsScreen`, real `GET /v1/projects`, loading/empty/error states |
| `/sources` | Searchable source library, file-type badges, source rows and processing/version status | `SourcesScreen`, upload/finalize against `POST /v1/sources/uploads`, immutable version list |
| `/skills` | Starter/organization/workspace skill cards, package descriptions, version detail, create menu, AI-author affordance | `SkillsScreen`, draft/validate/publish API path, scoped package metadata |
| `/projects/new` | Project type, brief, source selection, validation before create | `NewProjectModal`, real project command and selected ready source versions |
| `/projects/:id/canvas` | Three-column canvas: source/search rail, outline/content tabs, persistent Copilot panel, activity/todos, citation and proposal review | `Canvas`, durable event replay, typed content/outline DTOs, citation panel, accept/reject diff |
| Canvas overlays | Citation context, proposed diff, accept/reject, loading and unavailable states | `CitationPanel`, `DiffCard`, deterministic patch endpoints |
| `/export` and Settings | Export/preview action, review preferences, default format, keyboard command palette | Export action, `SettingsModal`, `CommandPalette` (`⌘K`/`Ctrl+K`) |

The reference also uses visible keyboard focus, compact monospace metadata labels, keyboard-dismissable overlays, and responsive collapse of the rail/Copilot. Those behaviors are retained in the React client.

## Implementation evidence

For each route, capture component tests and one e2e happy path plus permission, failure, reconnect, and empty-state coverage. Visual parity should be reviewed against extracted reference screens, but product-contract correctness takes priority over pixel imitation when the archive is ambiguous.
