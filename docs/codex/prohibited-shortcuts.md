# Prohibited shortcuts

- Replacing the central agent with a fixed semantic stage graph.
- Letting the agent write accepted content/status/database rows directly.
- Generic SQL/shell/filesystem/network tools in production.
- Trusting workspace/source IDs from model arguments.
- Loading all sources/skills/content into prompts.
- Treating checkpoints, vector index, or Langfuse as canonical product state.
- Mutable published skills/sources/content/templates.
- Last-write-wins content acceptance.
- Model-estimated progress percentages or fabricated citations.
- Unbounded retry/grader/self-repair loops.
- Swallowed errors, placeholder success, or fallback that changes semantics silently.
- Tests that only assert mocks were called.
- Disabling auth/tenant checks outside route layer.
- Updating code without required documentation/traceability updates.
- Marking a checklist done without executed evidence.
