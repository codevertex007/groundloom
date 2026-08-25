# Skills registry component

Owns skill identity, immutable versions/files, validation, scope, publication, deprecation, project selection, and runtime projections. Starter skills ship with releases; organization/workspace packages are stored and audited.

Commands: create draft, fork, repair/update draft, validate, request approval, publish, deprecate, select version. Fork copies only an authorized published package into a workspace-scoped draft and never publishes automatically. Repair creates the next immutable draft version and records its predecessor; publication never mutates bytes. Resolver returns only authorized active metadata/packages and pins project/run projections.

Required tests: YAML/frontmatter, trigger quality, path traversal, broken resources, oversized package, invalid/disallowed tool references, policy override attempts, secret scanning, role/approval, version pinning, concurrent publish, scope isolation, and agent load behavior.
