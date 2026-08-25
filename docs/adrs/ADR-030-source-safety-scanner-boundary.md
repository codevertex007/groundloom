# ADR-030: Source safety scanner boundary and terminal quarantine

## Status

Accepted — 2026-08-25

## Context

Uploaded source bytes are untrusted and must be checked before parsing or
indexing. Groundloom must remain credential-free locally while allowing a
deployment to use a managed malware scanner or isolated sidecar. Parser
failures and security findings have different retry and user-action semantics.

## Decision

Ingestion runs a bounded scanner stage after the source object is stored and
before parsing. The local scanner detects the standard antivirus fixture and
known active PDF/DOCX features without executing content. The deployment HTTP
adapter sends a bounded JSON request to a configured scanner sidecar and
accepts only `clean` or `quarantine` verdicts; outage, rejection, and malformed
responses are typed dependency/provider errors.

An unsafe verdict sets the immutable source version to terminal `quarantined`,
records `SOURCE_QUARANTINED`, emits a stage event, and prevents parsing,
embedding, or retrieval. Ingestion worker recovery preserves quarantine after
rollback and never converts it into a retryable parser failure.

## Consequences

- Local tests can prove the security state machine without a malware service.
- Production must configure and operate an external scanner sidecar or managed
  service; the local scanner is rejected by production settings validation.
- Parser structural errors remain `PARSE_FAILED` and retain their existing
  recovery semantics.
