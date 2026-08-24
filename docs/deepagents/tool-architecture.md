# Tool architecture

Tools are typed capability boundaries, not generic infrastructure access.

## Families

- Project/context: snapshot, active selection, configuration/version manifests.
- Retrieval: search authorized passages, read passage/neighbors, source conflicts.
- Content read: outline/version/block/citation views.
- Proposal: propose outline, block operations, citations, assessments.
- Validation: schema, structure, citation, policy, semantic quality request.
- Planning: write/update todos.
- Jobs: request export; inspect permitted job status.
- Skills: discover/read active skill packages; skill-author agent has separate draft tools.

## Rules

- Inputs/outputs are versioned Pydantic schemas with bounded sizes.
- Identity/scope comes from runtime context, never model arguments.
- Read outputs use opaque IDs and minimal data.
- Mutations require idempotency and produce non-canonical proposals unless explicitly deterministic/approved.
- Errors use the common taxonomy and say whether retry, revise input, ask user, or stop.
- Tool descriptions state when to use, when not to use, side effects, and permission/approval behavior.
- No generic SQL, unrestricted filesystem/object access, production shell, arbitrary URL fetch, or raw credentials.

Every tool has unit, authorization, schema, replay, size-bound, observability, and prompt-injection tests.
