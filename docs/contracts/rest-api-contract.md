# REST API contract

All endpoints are `/v1`, authenticated except health/auth callbacks, use JSON product DTOs, return correlation IDs, and never expose raw framework/database/provider structures. Writes accept `Idempotency-Key`; version-sensitive writes accept expected version.

Core resources:

```text
POST/GET /projects                         GET /projects/{id}
POST     /projects/{id}/threads/messages  GET /threads/{id}/events
GET      /threads/{id}/events/stream      POST /sources/{id}/versions
POST     /runs/{id}/cancel                POST /runs/{id}/resume
POST     /sources/uploads                 GET /sources/{id}
GET      /source-versions/{id}/passages/{passage_id}
POST     /skills                          POST /skills/ai-drafts
POST     /skill-versions/{id}/validate    POST /skill-versions/{id}/publish
POST     /patches/{id}/accept             POST /patches/{id}/reject
POST     /exports                         GET /exports/{id}
```

Use 400 invalid request, 401 unauthenticated, 403 authorized identity lacking action without existence leak, 404 accessible resource absent, 409 version/state/idempotency conflict, 422 domain validation, 429 budget/rate, 503 transient dependency. Error body follows `error-taxonomy.md`.

Before implementation, generate an OpenAPI document and contract tests for every operation, auth case, error, pagination, idempotency, and example. The OpenAPI is generated/validated from code but reviewed against this specification.
