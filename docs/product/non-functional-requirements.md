# Non-functional requirements

Targets are initial production objectives and must be measured before tightening.

## Reliability

- **NFR-REL-001:** Accepted domain mutations MUST survive API/worker restart.
- **NFR-REL-002:** Replaying a run/tool/job MUST not duplicate canonical mutations, publication, or export artifacts.
- **NFR-REL-003:** The client MUST recover public run events after reconnect using durable sequence replay.
- **NFR-REL-004:** Backup/restore exercises MUST demonstrate recovery of domain state, checkpoints, and artifact references.

## Performance

- **NFR-PERF-001:** Non-agent project/source/content queries target p95 < 500 ms under agreed baseline load.
- **NFR-PERF-002:** Agent runs target first durable visible activity within 2 seconds excluding queue saturation.
- **NFR-PERF-003:** Retrieval targets p95 < 2 seconds for the initial corpus envelope.
- **NFR-PERF-004:** Long model latency MUST not block API process capacity.

## Scale envelope for v1

Document and load-test assumptions: 100 workspaces, 1,000 active projects, 100k source versions, 10 concurrent agent runs, 20 concurrent ingestion/export jobs. Exceeding these numbers triggers capacity review, not silent degradation.

## Security/privacy

- No secrets in source, logs, traces, checkpoints, or client payloads.
- Sensitive trace payloads are redacted by workspace policy before export.
- Tenant isolation tests are release-blocking.
- Deletion/retention covers canonical and derived data with auditable completion.

## Cost

Every run records model/tool usage and cost attribution. Per-run and workspace budgets can stop additional optional agent work while preserving an intelligible partial result and resume path.

## Accessibility/compatibility

Critical UI journeys target WCAG 2.2 AA. Support current stable Chrome, Edge, Firefox, and Safari according to the release matrix.
