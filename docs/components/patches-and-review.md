# Patches and review component

A patch targets one base content version and contains typed operations: `insert_after`, `replace_block`, `delete_block`, `move_block`, and `replace_citations`. The service validates target ownership, schemas, operation conflicts, citations, limits, and policy, then stores a non-canonical proposal.

Accept requires reviewer permission and expected current/base version; it creates exactly one immutable content version and decision/outbox event. Reject records decision/reason and changes no canonical blocks. Stale base returns conflict with current version; automatic rebase is not assumed.

Required tests: every operation, mixed operations, invalid IDs/types, unauthorized citations, duplicate submit/accept, stale base, concurrent accept, reject immutability, validation failure, audit/provenance, and UI diff DTO accuracy.
