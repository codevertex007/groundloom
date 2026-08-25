# REST API contract

All endpoints are `/v1`, authenticated except health/auth callbacks, use JSON product DTOs, return correlation IDs, and never expose raw framework/database/provider structures. Writes accept `Idempotency-Key`; version-sensitive writes accept expected version.

Core resources:

```text
POST/GET /projects                         GET /projects/{id}
GET      /projects/page?limit=&cursor=     (bounded keyset page)
GET      /audit-events?limit=&cursor=      (admin-only bounded audit page)
POST     /projects/{id}/threads/messages  GET /threads/{id}/events
GET      /threads/{id}/events/stream      POST /sources/{id}/versions
POST     /runs/{id}/cancel                POST /runs/{id}/resume
GET      /runs/{id}/approvals             POST /approvals/{id}/resolve
POST     /sources/uploads                 GET /sources/{id}
GET      /source-versions/{id}/passages/{passage_id}
POST     /skills                          POST /skills/ai-drafts
POST     /delegated-tasks/{id}/retry      POST /runs/{id}/delegated-tasks/reconcile
POST     /skill-versions/{id}/validate    PUT  /skill-versions/{id}/repair
POST     /skill-versions/{id}/publish
POST     /patches/{id}/accept             POST /patches/{id}/reject
POST     /exports                         GET /exports/{id}
POST     /source-versions/{id}/index-rebuilds  GET /index-rebuilds/{job_id}
GET/PUT  /workspace/retention-policy
GET/PUT  /workspace/preferences
```

Use 400 invalid request, 401 unauthenticated, 403 authorized identity lacking action without existence leak, 404 accessible resource absent, 409 version/state/idempotency conflict, 422 domain validation, 429 budget/rate, 503 transient dependency. Error body follows `error-taxonomy.md`.

The project message command serializes active mutation turns with a partial
unique database index. A different message while a run is queued, running, or
waiting returns `409 INVALID_STATE`; the same idempotency key replays the
existing run.

Before implementation, generate an OpenAPI document and contract tests for every operation, auth case, error, pagination, idempotency, and example. The OpenAPI is generated/validated from code but reviewed against this specification.

`GET /projects/page` is the paginated project-card query. `limit` is bounded
to 1..100 and defaults to 50. `next_cursor` is an opaque workspace-scoped
keyset cursor; clients must not construct or interpret it. The legacy
`GET /projects` list remains available for compatibility but is not used by
the reference client.

Export creation is idempotent and returns queued in staging/production;
export_worker.py advances queued to rendering, storing, completed, or failed.
The credential-free development adapter performs one inline worker pass unless
GROUNDLOOM_EXPORT_INLINE_LOCAL=false. Project deletion always returns a
durable pending request and is completed only by the retention worker.
Plan approval is represented by a durable approval request. Resolving an
approval emits `approval.resolved` and resumes the same run/thread; rejected
plans terminate the run without creating a canonical content version. Runs
also expose redacted usage and bounded budget metadata in `RunOut`.
Workspace preferences are typed, versioned, audited, and idempotent. Project
configuration pins the effective workspace defaults; explicit project defaults
override them within policy bounds. The UI reads and writes these preferences
through the API rather than maintaining client-only settings.

Skill repair never edits an existing version. `PUT
/skill-versions/{id}/repair` validates the caller's workspace scope, creates the
next draft version for the same skill, records `repaired_from_version_id`, and
accepts `Idempotency-Key`. Published bytes cannot be repaired in place.

`POST /skills/{id}/fork` copies an authorized published starter, organization,
or visible workspace skill into a new workspace-scoped draft. The fork never
publishes automatically, accepts an optional replacement slug/name/description,
and supports the same idempotent replay boundary.

Transactional outbox rows are not public REST resources. The configured
`outbox_worker.py` publishes their normalized envelopes to the deployment sink
with at-least-once delivery; each envelope carries its stable outbox ID for
consumer deduplication. The disabled local sink is never reported as success.

`GET /audit-events` is restricted to `workspace_admin` and
`organization_admin` memberships. It returns only the append-only event's safe
actor/action/target/result/correlation/summary/timestamp fields and uses an
opaque keyset cursor bounded to 1..100 items. Reading the stream appends an
`audit.read` event after the page is materialized; audit records never expose
raw payloads, prompts, source text, credentials, or provider responses.
