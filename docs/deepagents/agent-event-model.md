# Agent event model

Internal runtime events are normalized into stable product events.

Families: `run.started/completed/failed/cancelled`, `todo.created/updated`, `tool.started/completed/failed`, `subagent.started/progress/completed/failed`, `question.required`, `plan.proposed`, `approval.required/resolved`, `patch.proposed`, `validation.started/finding/completed`, `artifact.delta` where safe, and `budget.warning/stopped`.

Events contain stable ID, run sequence, schema version, project/run/thread, timestamp, public payload, and optional todo/module/block/tool correlation. Do not emit hidden reasoning, raw prompts, credentials, unbounded source text, or provider-specific objects. Token deltas may be ephemeral enhancements; durable state/proposals remain authoritative.

Replay and duplicate suppression are tested across reconnect, API restart, and worker handoff.
