# REST API contract

All endpoints are `/v1`, authenticated except health/auth callbacks, use JSON product DTOs, return correlation IDs, and never expose raw framework/database/provider structures. Writes accept `Idempotency-Key`; version-sensitive writes accept expected version.

Core resources:

```text
POST/GET /projects                         GET /projects/{id}
POST     /projects/{id}/threads/messages  GET /threads/{id}/events
GET      /threads/{id}/events/stream      POST /sources/{id}/versions
POST     /runs/{id}/cancel                POST /runs/{id}/resume
GET      /runs/{id}/approvals             POST /approvals/{id}/resolve
POST     /sources/uploads                 GET /sources/{id}
GET      /source-versions/{id}/passages/{passage_id}
POST     /skills                          POST /skills/ai-drafts
POST     /delegated-tasks/{id}/retry      POST /runs/{id}/delegated-tasks/reconcile
POST     /skill-versions/{id}/validate    POST /skill-versions/{id}/publish
POST     /patches/{id}/accept             POST /patches/{id}/reject
POST     /exports                         GET /exports/{id}
POST     /source-versions/{id}/index-rebuilds  GET /index-rebuilds/{job_id}
GET/PUT  /workspace/retention-policy
GET/PUT  /workspace/preferences
```

Use 400 invalid request, 401 unauthenticated, 403 authorized identity lacking action without existence leak, 404 accessible resource absent, 409 version/state/idempotency conflict, 422 domain validation, 429 budget/rate, 503 transient dependency. Error body follows `error-taxonomy.md`.

Before implementation, generate an OpenAPI document and contract tests for every operation, auth case, error, pagination, idempotency, and example. The OpenAPI is generated/validated from code but reviewed against this specification.

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
