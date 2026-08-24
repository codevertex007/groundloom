# Monitoring and alerting

Dashboards: API traffic/errors/latency; database pools/locks/storage; checkpoint/outbox lag; worker queue/lease/failure; ingestion stages; agent/model/tool/subagent latency/errors/cost; retrieval latency/no-evidence; validations; exports; SSE reconnect/replay; auth denials/security signals.

Alerts must be actionable with severity, threshold/window, owner, linked runbook, and deduplication. Page for tenant/security/data-loss/complete outage and sustained critical queue/database failures; ticket for trends/cost/quality regressions. Never include raw sensitive source content in alert payloads.
