# Projects component

Owns projects, immutable configuration versions, source/skill selections, status events, and current outline/content pointers. Create validates type/brief/defaults and authorized ready source/published skill versions, commits the initial configuration, then starts the primary agent thread after commit.

Commands: create, update configuration (new version), archive/restore, request deletion, select source/skill versions. Queries: grid/detail/snapshot and version history. Agent gets a compact snapshot tool, not general mutation.

Invariants: workspace scope; immutable configuration; historical run pins unchanged; current pointers reference same project; grid derives from domain/run projections. Definition of done: migration, repositories/services, DTOs, auth/idempotency, outbox, snapshot tool, unit/contract/integration/e2e tests, telemetry, and updated traceability.
