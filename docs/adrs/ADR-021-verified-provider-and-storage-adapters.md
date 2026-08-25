# ADR-021: Verified provider, checkpoint, telemetry, and object-storage adapters

**Status:** Accepted  
**Date:** 2026-08-25

## Decision

Groundloom exposes narrow adapters for the model runtime, Postgres checkpointer,
Langfuse telemetry, and S3-compatible object storage. The local adapter remains
deterministic and filesystem/SQLite-backed for credential-free development. The
production configuration rejects local model, telemetry, object storage, and
checkpoint implementations before serving traffic.

The Deep Agents runtime is constructed only when the configured provider is
non-local and the optional pinned `agent` dependencies are installed. Its
harness profile excludes unrestricted filesystem, shell, network, and generic
delegation tools. Canonical mutations still go through Groundloom services and
proposal/accept commands.

## Rationale and consequences

This preserves a runnable local vertical slice while preventing a local fake
from being mistaken for production readiness. Provider packages are optional
because they require deployment credentials and, for Postgres checkpoints,
network/database access. Their APIs were verified against the pinned package
versions in `pyproject.toml`; deployment still requires live integration and
failure/recovery evidence.

The object-store adapter owns binary bytes and validates server-derived keys.
Its SDK client uses bounded standard retries with explicit connect/read
timeouts, and maps every provider failure to the stable Groundloom error
taxonomy so credentials, provider response bodies, and SDK exception details
never cross the API boundary. Local development may omit server-side
encryption; production configuration requires AES-256 or AWS KMS and the
adapter propagates the selected encryption headers on writes.
The Postgres checkpointer owns execution state only. Langfuse receives redacted
events and is not product storage.
