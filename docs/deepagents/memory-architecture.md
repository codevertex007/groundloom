# Memory architecture

Memory contains approved stable preferences and workspace terminology/policy, such as concise style, default locale, audience conventions, or repeated workflow preferences. It excludes source text, current drafts, run progress, unresolved instructions from documents, and facts already represented in domain state.

Namespace at least by `(assistant_id, workspace_id, user_id)`. Organization policy is application-written/read-only. User/workspace writes use typed operations, provenance, audit, overwrite/delete semantics, and approval where configured. Retrieval is scoped before the model and bounded.

Memory candidates should be presented when material rather than learned from every interaction. Rejected edits and untrusted source statements cannot become memory automatically. Tests cover cross-tenant/user denial, stale preference correction, deletion, prompt injection, and context budget behavior.
