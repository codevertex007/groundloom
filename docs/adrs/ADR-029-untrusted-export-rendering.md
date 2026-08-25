# ADR-029: Escape untrusted content in deterministic exports

## Status

Accepted — 2026-08-25

## Context

Source documents, user-authored briefs, and model output are untrusted data.
Groundloom's deterministic HTML and DOCX renderers serialize those values into
formats that interpret markup. Treating markup as presentation would create an
active-content or document-injection path during preview or download.

## Decision

All HTML and DOCX text nodes are escaped with an XML/HTML-safe encoder before
serialization. The renderer emits only fixed Groundloom tags and does not
interpret links, scripts, event attributes, embedded resources, or source
markup. Markdown remains a plain text export format; PDF text is bounded and
serialized through the existing safe literal encoder.

## Consequences

- Exported content preserves the literal text of markup instead of executing it.
- The deterministic renderer remains suitable for local tests and worker
  execution without a browser or general-purpose HTML engine.
- Rich active content requires a separately reviewed, sanitized capability and
  cannot be introduced by changing a template string.
