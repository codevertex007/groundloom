# Project and resource lifecycles

## Project

`draft → active → archived`; deletion enters `deletion_pending → deleted`. Generation activity is represented by runs, not by overloading project status.

## Run

`queued → running ↔ waiting_for_user/approval → completed|failed|cancelled`. A failed/cancelled run may be resumed only according to its failure policy and checkpoint. Terminal status is append-only.

## Source version

`uploaded → scanning → parsing → normalizing → indexing → ready`, with `failed` at each recoverable stage and `quarantined` for security failures. A new source revision creates a new version; it never returns an old version to `uploaded`.

## Skill version

`draft → validating → valid|invalid → approval_pending → published → deprecated`. Published bytes are immutable; repair creates a new draft version.

## Proposal

`draft → validated → presented → accepted|rejected|superseded|conflicted`. Only validated/presented proposals can be accepted. Acceptance is exactly once.

## Export

`queued → rendering → storing → completed|failed|cancelled|expired`. Artifact expiry does not remove the export record or source version references.

All transitions MUST be authorized, idempotent, timestamped, and represented by an append-only status event. Invalid transitions return a typed conflict rather than coercing state.
