# Data retention and deletion

Define workspace-configurable policy within organization/legal limits for sources/versions, projects/content, agent messages/checkpoints/scratch, traces/evals, exports, audit, and backups. Legal hold overrides deletion and is authorized/audited.

Deletion is a durable coordinated workflow: mark inaccessible/pending; revoke URLs; delete canonical records/objects according to integrity order; remove derived index/cache/scratch/checkpoints/eligible traces; record completion/failures; respect backup expiry. Users receive status without exposing internal paths. Test retry and partial failure.

The local implementation provides this project-scoped slice through the project
deletion request and deletion status endpoints. It persists a DeletionRequest,
moves the project to deletion_pending, cancels active runs, removes unshared
source versions and derived blocks/chunks, removes content/run/export records
and local checkpoints, deletes object-store artifacts through the scoped
adapter, and records RetentionDeletionRequested and
RetentionDeletionCompleted. The retention worker claims the request with a
bounded lease. A workspace RetentionPolicy legal hold blocks the workflow and
is audited; failed object or database steps remain retryable. Production still
requires review of backup expiry, trace deletion, external checkpoint deletion,
and encrypted object-store lifecycle policies.

Workspace administrators configure the local policy through the authorized
workspace retention-policy endpoints. The policy validates bounded retention
periods and legal-hold state, and updates are audited and emitted through the
outbox before workers consume them.
