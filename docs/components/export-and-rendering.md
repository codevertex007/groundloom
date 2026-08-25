# Export and rendering component

Owns immutable render templates/versions, export request/job, artifact metadata, expiry, and download authorization. Rendering consumes an accepted immutable content version and template/config version; no agent participates in rendering.

Workers render in an isolated environment, validate output, store once by idempotency key, and emit status events. HTML/PDF/DOCX support is adapter-based; initial target is PDF + DOCX pending `OQ-001`. HTML and DOCX renderers escape all user/source/model text before serialization; markup is never treated as executable content.

Required tests: exact version selection, duplicate request/replay, template failure, worker death, malicious content/assets, output validation, large document bounds, cancellation, expiry, short-lived artifact capabilities (missing/tampered/wrong-artifact/revoked-membership), signed-download permission, and provenance metadata.
