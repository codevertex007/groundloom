# SSE event catalog

Envelope:

```json
{"event_id":"evt_...","seq":12,"schema_version":1,"type":"todo.updated","project_id":"...","run_id":"...","thread_id":"...","occurred_at":"...","payload":{}}
```

Required types: `run.started`, `run.completed`, `run.failed`, `run.cancelled`, `run.waiting`; `todo.created/updated`; `question.required`; `plan.proposed`; `approval.required/resolved`; `tool.started/completed/failed`; `subagent.started/progress/completed/failed`; `patch.proposed/accepted/rejected/conflicted`; `validation.started/finding/completed`; `source.stage.changed`; `export.stage.changed/completed/failed`; `budget.warning/stopped`.

Sequence is monotonic per run and persisted before publish. Reconnect supplies last event ID/sequence; `/events/stream` replays later persisted events in SSE format and the deployment broadcaster can continue the stream. The local synchronous adapter closes after the durable replay. Consumers ignore unknown event types/fields for forward compatibility. Events are bounded/redacted and do not contain chain-of-thought or entire source documents.
