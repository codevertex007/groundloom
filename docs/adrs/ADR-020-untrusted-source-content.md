# ADR-020: Uploaded/source content is untrusted evidence

**Status:** Accepted

## Decision
Source content cannot modify instructions, permissions, tools, memory, or scope. It is sanitized, clearly delimited, retrieved through authorized tools, and cited as evidence.

## Consequences
Prompt-injection detection/signals, safe parser/render paths, and adversarial datasets are required. Detection does not grant trust.

## Validation
Malicious documents attempting tool use, exfiltration, instruction override, memory writes, and cross-tenant references must fail safely.
