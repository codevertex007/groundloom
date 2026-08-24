# ADR-005: Typed content blocks

**Status:** Accepted

## Context
A mutable Markdown blob weakens diffs, citations, review, structured export, and concurrent editing.

## Decision
Store ordered typed blocks with stable IDs, validated payloads, citations, provenance, and immutable content versions.

## Consequences
Editors/renderers require block adapters and migrations; arbitrary formatting is constrained intentionally.

## Validation
Schema, round-trip rendering, diff, citation, ordering, and version-history tests.
