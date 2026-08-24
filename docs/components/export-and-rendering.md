# Export and rendering component

Owns immutable render templates/versions, export request/job, artifact metadata, expiry, and download authorization. Rendering consumes an accepted immutable content version and template/config version; no agent participates in rendering.

Workers render in an isolated environment, validate output, store once by idempotency key, and emit status events. HTML/PDF/DOCX support is adapter-based; initial target is PDF + DOCX pending `OQ-001`.

Required tests: exact version selection, duplicate request/replay, template failure, worker death, malicious content/assets, output validation, large document bounds, cancellation, expiry, signed-download permission, and provenance metadata.
