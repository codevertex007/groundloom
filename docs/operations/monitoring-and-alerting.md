# Monitoring and alerting

Dashboards: API traffic/errors/latency; database pools/locks/storage; checkpoint/outbox lag; worker queue/lease/failure; ingestion stages; agent/model/tool/subagent latency/errors/cost; retrieval latency/no-evidence; validations; exports; SSE reconnect/replay; auth denials/security signals.

Minimum alert thresholds for the first deployment are: API 5xx above 2% for
5 minutes, p95 API latency above 1 second for 10 minutes, oldest queued job
above 5 minutes, lease expiry/retry rate above 5%, provider failure rate above
10%, object-store health degraded for 2 minutes, and any cross-tenant/auth
failure. Alerts link to correlation IDs and runbooks but never include source
text, tokens, prompts, artifacts, or credentials.

Alerts must be actionable with severity, threshold/window, owner, linked runbook, and deduplication. Page for tenant/security/data-loss/complete outage and sustained critical queue/database failures; ticket for trends/cost/quality regressions. Never include raw sensitive source content in alert payloads.
