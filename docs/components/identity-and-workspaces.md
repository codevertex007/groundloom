# Identity and workspaces component

Owns users, workspaces, memberships/roles, invitations where implemented, service identities, and policy/default references. Authentication provider details stay behind an adapter; authorization decisions use current durable membership.

Membership changes immediately affect new requests/tool calls and invalidate or deny approvals that require lost roles. Service workers use scoped identities; operators do not gain tenant content access by default.

Required tests: workspace creation, membership lifecycle, role matrix, revoked membership during run/approval, ID enumeration, service identity, audit events, row-level policy where used, and cross-tenant tests across every repository.
