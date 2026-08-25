# Configuration contract

Configuration groups: application/environment, database/checkpointer, object storage, worker/lease, model profiles, embedding/reranking, Langfuse/telemetry, upload/parser limits, agent/context/budget limits, security/retention, and feature flags.

Every setting has type, default where safe, required environments, secret classification, validation, and reload policy. Production refuses startup on missing secrets, invalid public URLs, unsafe CORS, disabled auth, absent encryption configuration, or in-memory checkpoint/storage configuration.

Feature flags do not bypass authorization/invariants and have owner, purpose, default, creation/removal date, metrics, and rollback behavior. Log a redacted effective configuration fingerprint, not secret values.

The local defaults are explicit: SQLite domain state, a filesystem object store,
local deterministic agent runtime, local JSON checkpoints, and local redacted
telemetry. Deployment settings select `checkpoint_backend=postgres`,
`object_store_backend=s3`, a configured model provider, and
`telemetry_provider=langfuse`; production startup rejects any local substitute.
Optional dependency groups are `agent`, `storage`, and `observability`.
Provider calls use at most `agent_max_attempts` (default 3) with bounded
exponential backoff; cancellation is checked before each retry.
Embedding calls use the configured `embedding_provider`, model, fixed vector
dimension, endpoint, and timeout. `local` uses deterministic hashing for
credential-free development. `openai`/`openai-compatible` uses a narrow
OpenAI-compatible `/embeddings` adapter and requires an API key; provider
outages and malformed dimensions become typed redacted dependency errors.
`retrieval_index_backend=auto` selects the local JSON index for SQLite and the
pgvector derived index for PostgreSQL. Production rejects an explicit local
index. Migration `015_pgvector_source_embeddings` owns the deployment table;
the migration role must be able to use an installed pgvector extension.
Reranking defaults to deterministic local overlap/phrase scoring. The optional
`cohere-compatible` reranker uses a bounded `/rerank` adapter with an explicit
model, API key, endpoint, and timeout; missing keys, outages, and malformed
scores are typed failures and never silently fall back to a different provider.
Semantic evaluation defaults to the deterministic rubric grader. The optional
`openai-compatible` evaluator uses bounded structured JSON from a
`/chat/completions` adapter with an explicit model, API key, endpoint, and
timeout; it never replaces deterministic citation or structure checks.
Source safety defaults to deterministic local checks for development, including
the standard antivirus fixture, active PDF actions, and active/macro-enabled
DOCX features. The deployment `http` scanner adapter posts bounded source
bytes to a configured scanner sidecar and accepts only `clean` or `quarantine`
verdicts; outages and malformed responses are typed failures. Production
rejects the local scanner setting. Multipart uploads are read in bounded
chunks and stop once `max_upload_bytes` is exceeded; the endpoint never loads
an unbounded file into memory before applying the upload limit.
OCR defaults to an explicit local-unavailable adapter. Image-only PDFs enter
the `ocr` ingestion stage and fail with a typed configuration error unless an
HTTP-compatible provider is configured with `GROUNDLOOM_OCR_BASE_URL`,
`GROUNDLOOM_OCR_API_KEY`, bounded timeout, and bounded output size. The sidecar
receives base64 source bytes and must return a non-empty `{text}` object; its
provider response and credentials never cross the product error boundary.
S3-compatible storage calls use `object_store_max_attempts` (default 3) with
`object_store_connect_timeout_seconds` (default 5) and
`object_store_read_timeout_seconds` (default 30). Local/MinIO development may
use `object_store_sse_mode=none`; production requires `AES256` or
`aws:kms`, and KMS mode requires `GROUNDLOOM_OBJECT_STORE_KMS_KEY_ID`.
`put_object` applies the configured server-side encryption headers. Storage SDK
failures are translated to typed retryable dependency errors; provider
exception details are never returned or logged as product errors.
`agent_inline_local=true` is the explicit local/test convenience default. It
must be disabled for production; staging/production agent runs are queued for
the durable agent worker and are never completed synchronously by the API.
`auth_mode=local` is limited to development/test. Staging and production use
the signed runtime-context adapter (`auth_mode=hmac`) or a deployment-provided
OIDC/JWT implementation at the same boundary; raw identity headers are ignored
in those environments.
Production also requires a 32-character auth secret, HTTPS public URL,
non-local CORS origins, and complete Langfuse credentials when Langfuse is
selected. Production PostgreSQL migrations install forced workspace RLS;
application requests set `app.workspace_id` transaction-locally after trusted
membership resolution. Leased workers use
`GROUNDLOOM_WORKER_DATABASE_URL` with the dedicated `groundloom_worker`
PostgreSQL role for cross-workspace queue claims; the API URL must use a
different non-owner role. `GROUNDLOOM_MIGRATION_DATABASE_URL` must use the
separate `groundloom_migrator` role for schema ownership and RLS installation;
the migration process also initializes the LangGraph checkpoint schema, while
the API and worker roles receive runtime DML privileges only. The
transaction-local service marker is metadata only, and the production API role
must not be the policy-bypassing owner.
Export download URLs are short-lived HMAC capabilities containing the issuing
user, trusted workspace, and exactly one export ID. The download endpoint
revalidates active membership and artifact expiry before reading the object;
the local adapter derives a clearly development-only signer from the local
workspace when no auth secret is configured. `download_token_ttl_seconds` is
bounded to one hour in the settings schema.
