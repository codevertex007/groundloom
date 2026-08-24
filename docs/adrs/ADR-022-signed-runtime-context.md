# ADR-022: Signed runtime identity context

**Status:** Accepted  
**Date:** 2026-08-25

## Decision

Local and test adapters may use seeded identity/workspace headers. Staging and
production require a signed bearer context containing only the authenticated
subject, workspace scope, and expiry. The API verifies the signature and
membership before any service or agent reasoning; request headers cannot
override the verified scope.

The adapter is intentionally narrow so an OIDC/JWT verifier can replace it at
deployment without changing service contracts. Tokens are never logged or
passed to the model. Production startup requires `auth_mode=hmac` and a secret.

## Consequences

The repository remains credential-free locally while preventing the unsafe
header-based tenant selection from being used as a production identity system.
The HMAC adapter is not an identity provider, key rotation service, or user
directory; production operations must supply those controls or replace the
verifier with the selected identity provider integration.
