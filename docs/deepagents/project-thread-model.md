# Project thread model

Primary thread key: `project:{project_id}:primary`. Create after the project transaction commits. Individual user requests create `agent_run` records within the stable thread; detached maintenance may use `project:{project_id}:background:{run_id}`.

Runtime context carries trusted `user_id`, `workspace_id`, `project_id`, `thread_id`, `run_id`, roles, locale, request correlation, budgets, and feature-policy flags. The model cannot set these values.

State extends Deep Agent state only with compact execution references: phase hint, todos, active module/task IDs, current proposal ID, validation summary, pending approval, and pinned run config ID. Full sources/content/skills stay in domain storage/backends.

Checkpoint requirements:

- production Postgres checkpointer;
- same thread on interrupt resume;
- run metadata identifies compiled agent/prompt/tool versions;
- incomplete tool-call pairs repaired according to framework behavior;
- retention/deletion coordinated with project policy;
- no UI grid/query built by interpreting checkpoint messages.

Concurrent mutation turns for one thread are serialized or explicitly cancel/replace; never race silently.
