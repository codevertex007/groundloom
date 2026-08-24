# Model and provider strategy

Use a provider-neutral adapter and configuration profiles. The primary model must reliably plan, use tools, maintain long tasks, follow scoped instructions, and produce structured proposals. Specialist models may optimize cost/latency for bounded research, audit, or classification tasks only after evaluation.

Profiles define provider/model, reasoning setting, temperature where applicable, timeouts, retries, context/output limits, supported structured/tool features, and cost budget. Provider-specific prompt/tool suffixes remain in harness profiles, not domain requirements.

Fallback is allowed only when capabilities and evaluation gates are satisfied; record the actual model/provider. Never silently downgrade a safety/quality-critical task. Pin model profile per run for provenance. Upgrades require offline trajectory/retrieval/content evals, staging soak, cost/latency comparison, and a rollback path.
