# Planning and progress

Planning is adaptive. Small questions may execute directly. Multi-step generation, broad research, or independent modules should create todos with stable IDs, description, state, optional module/agent/job correlation, dependencies, and completion evidence.

Todo states: `pending`, `in_progress`, `blocked`, `waiting_for_user`, `completed`, `cancelled`, `failed`. Only actual status changes emit progress events. At most one primary-agent task is `in_progress`, while delegated children may execute concurrently.

The UI may calculate percentage from configured weights and known tasks; the model cannot write an arbitrary percentage. Replanning preserves completed evidence and explains materially changed scope. A task is complete only when its stated outcome exists and required checks pass.

Trajectory tests verify the agent avoids needless plans for trivial work, plans complex work, updates status after observations, exposes blockers, and does not mark failed/unchecked output complete.
