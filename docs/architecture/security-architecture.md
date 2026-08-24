# Security architecture

## Threats

Cross-tenant access, malicious uploads, prompt injection, tool abuse, data exfiltration, privilege escalation through skills/memory, unsafe rendering, SSRF, replayed side effects, sensitive telemetry, supply-chain compromise, and operator overreach.

## Controls

- Authenticate at the API; derive trusted runtime identity and workspace membership.
- Authorize in routes and every service/tool/repository boundary; default deny.
- Scope retrieval, skills, memory, files, checkpoints, artifacts, and traces by trusted context.
- Treat documents, user content, and model output as untrusted data.
- Validate typed inputs/outputs; separate proposal tools from commit commands.
- Malware scan and sanitize uploads; sandbox risky parsers/renderers; block active content.
- No unrestricted production shell/network. Any code sandbox gets resource/network/filesystem limits and short-lived credentials.
- Organization policy and published skills are immutable/read-only to runtime agents.
- Redact telemetry and use a secret manager.
- Audit security-sensitive reads/writes, approvals, membership/policy changes, and exports.

Security tests in `validation/security-test-plan.md` block release.
