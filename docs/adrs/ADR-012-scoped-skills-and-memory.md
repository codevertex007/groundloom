# ADR-012: Scoped skills and memory through controlled backends

**Status:** Accepted

## Decision
Use scoped, versioned skill routes and user/workspace memory namespaces with read-only organization policy and project-pinned skill projections.

## Consequences
Resolver/publication/memory-write governance is required; virtual filesystem is not a security boundary by itself.

## Validation
Scope, path, publication, pinning, injection, memory eligibility, deletion, and cross-tenant tests.
