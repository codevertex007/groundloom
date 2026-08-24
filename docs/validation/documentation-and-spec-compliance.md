# Documentation and specification compliance

CI should include a lightweight specification validator that:

- resolves relative Markdown links and flags missing referenced files;
- detects duplicate requirement/ADR/checklist IDs;
- verifies active requirement IDs appear in the traceability matrix;
- checks ADR filename/number/status consistency;
- validates embedded JSON/YAML examples where marked machine-readable;
- compares generated OpenAPI/tool/event schemas with approved contract snapshots;
- requires documentation impact metadata for changed API/tool/event/schema/middleware paths;
- reports completed checklist items lacking evidence references.

Architecture tests should enforce module dependency rules, absence of generic production tools, and that canonical mutation commands are not registered as primary-agent tools. These executable checks complement human review; they do not infer intent when a behavioral document/code conflict exists.
