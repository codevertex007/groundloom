# Data retention and deletion

Define workspace-configurable policy within organization/legal limits for sources/versions, projects/content, agent messages/checkpoints/scratch, traces/evals, exports, audit, and backups. Legal hold overrides deletion and is authorized/audited.

Deletion is a durable coordinated workflow: mark inaccessible/pending; revoke URLs; delete canonical records/objects according to integrity order; remove derived index/cache/scratch/checkpoints/eligible traces; record completion/failures; respect backup expiry. Users receive status without exposing internal paths. Test retry and partial failure.
