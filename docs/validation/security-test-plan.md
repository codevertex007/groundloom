# Security test plan

Test authentication/session, role matrix, object enumeration, wrong-workspace IDs at every layer, retrieval filter bypass, checkpoint/thread guessing, skill/memory path traversal, organization publication, artifact URL access, operator/service identity, audit access, and membership revocation.

Adversarial uploads include malware fixtures, MIME spoof, archive bomb/oversize, parser exploit samples where safe, active content, prompt injection, secret-like text, external links/SSRF attempts, and malicious render payloads. Model/tool attacks request raw SQL/shell/network, scope changes, memory poisoning, policy override, and data exfiltration.

Also run dependency/container/secret scans and threat-model review. Critical/high findings block release unless independently demonstrated non-exploitable and documented with owner/expiry.
