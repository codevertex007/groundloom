# Change impact protocol

| Change | Mandatory review/update |
|---|---|
| API DTO/endpoint | REST contract, OpenAPI, client, contract/e2e tests, versioning |
| Tool | tool contract, agent prompt/factory, permissions, trajectory tests, tracing |
| Event | SSE/domain catalog, replay projection/client tests, schema version |
| Database | data/component spec, migration, repositories, backup/restore compatibility |
| Prompt/model | version record, evaluation dataset/results, rollback profile |
| Skill/memory | scope/policy specs, security tests, provenance |
| Middleware/order | ADR if durable, agent spec, bypass/order/checkpoint tests |
| UI behavior | screen inventory, capability map, acceptance/e2e/accessibility |
| Security policy | threat architecture, role matrix, tests, operations/incident implications |

Codex must include this impact assessment in its handoff even when the answer is “no change” for a row.
