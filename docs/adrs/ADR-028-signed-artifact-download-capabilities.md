# ADR-028: Short-lived signed artifact download capabilities

## Status

Accepted — 2026-08-25

## Context

Export artifacts live in the canonical object store, but the product API must
not expose a reusable object-store credential or make a long-lived URL the
authorization boundary. A download must remain scoped to the trusted
workspace, the active user membership, and one immutable export artifact.

## Decision

Completed export DTOs issue a short-lived HMAC capability containing the user,
workspace, export ID, token kind, and expiry. The signer uses the production
auth secret; local development uses an explicit deterministic local signer
only when no auth secret is configured. The download endpoint validates the
signature and artifact ID before resolving membership, then checks artifact
status/expiry and reads only the stored key through the object-store adapter.
Successful downloads emit a safe audit event. Missing, expired, tampered, or
wrong-artifact tokens share the unauthenticated boundary and do not reveal
whether an artifact exists.

## Consequences

- Download links expire after the bounded configured TTL (five minutes by default).
- Revoked workspace membership stops further downloads even while a capability
  is otherwise unexpired.
- Clients must use the `download_url` returned by the export DTO; raw artifact
  paths and workspace headers are not accepted as download authorization.
- Production still needs secret rotation and object-store lifecycle/backup
  policy review as deployment evidence.
