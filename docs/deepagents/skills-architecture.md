# Skills architecture

Scopes map to virtual routes: starter (built-in read-only), organization (published read-only), workspace (draft/published), and project-active (pinned projection). Store full packages—`SKILL.md` plus permitted relative resources—not prompt snippets.

At run start, resolve selected versions and project them immutably. The primary agent receives metadata and loads full instructions on demand. Frontmatter includes name, description/trigger, version metadata, compatible tools/capabilities, and optional evaluation references.

Validation checks frontmatter, unique slug, trigger specificity, size, safe relative paths, valid tool references, disallowed secrets/instructions, sample trigger/non-trigger cases, and policy compatibility. AI skill author creates drafts only. Organization publication requires role and approval.

Skill instructions never override tenant/security/system policy. Published versions are immutable; edit/fork creates a new version. Record selected/loaded skill versions in traces and run provenance.
