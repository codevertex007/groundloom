# Domain event catalog

Internal events use past-tense names and versioned payloads: `ProjectCreated`, `ProjectConfigurationVersionCreated`, `SourceVersionUploaded`, `SourceStageChanged`, `SourceVersionReady`, `SkillVersionPublished`, `RunStarted/Completed/Failed/Cancelled`, `ApprovalRequested/Resolved`, `OutlineProposed/Accepted`, `PatchProposed/Accepted/Rejected/Conflicted`, `ContentVersionCreated`, `ValidationCompleted`, `ExportRequested/Completed/Failed`, `RetentionDeletionRequested/Completed`.

Envelope includes event ID/type/version, aggregate ID/type/version, workspace, actor, correlation/causation, occurred time, and minimal payload. Domain transaction and outbox insert are atomic. Consumers are idempotent and tolerate additive fields. Public SSE events are projections, not necessarily one-to-one copies.
