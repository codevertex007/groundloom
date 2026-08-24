# Roles and permissions

## Roles

- **Viewer:** read permitted workspace projects/sources/content and download eligible artifacts.
- **Author:** viewer rights plus create projects, message agents, upload sources, create proposals, and export.
- **Reviewer:** author rights plus accept/reject content proposals and record review overrides.
- **Workspace admin:** membership, workspace skills, defaults, retention, model/policy configuration.
- **Organization admin:** organization skill publication and organization policy.
- **Service operator:** infrastructure/health access; no tenant content access by default.

## Enforcement

- **SEC-AUTH-001:** Identity and workspace membership MUST be resolved server-side.
- **SEC-AUTH-002:** Every query and mutation MUST enforce workspace scope in the service/repository; route checks alone are insufficient.
- **SEC-AUTH-003:** Agent tools MUST derive scope from trusted runtime context and reject model-supplied attempts to broaden it.
- **SEC-AUTH-004:** Organization skill publication, memory writes, and configured irreversible/external actions MUST require explicit role/approval.
- **SEC-AUTH-005:** Signed download access MUST be short-lived and scoped to one authorized artifact.
- **SEC-AUTH-006:** Authorization denials MUST not reveal whether an inaccessible object exists.

Default deny applies when a role/action pairing is absent. Test each tool and service with allowed, wrong-workspace, revoked-membership, and invented-ID cases.
