"""Groundloom's single Deep Agents composition root.

This module owns model, prompt, tool, middleware, skill, subagent, checkpoint,
and streaming composition. Reusable policy primitives live in
``groundloom_harness``; backend capabilities arrive through a typed adapter.
"""

from typing import Any

from groundloom_harness import DEFAULT_EXCLUDED_TOOLS, BudgetCounter
from groundloom_harness.streaming import consume_provider_stream

from ..config import Settings
from .contracts import (
    AgentConfigurationError,
    AgentDefinition,
    AgentRuntimeContext,
    CancelCheck,
    ProgressCallback,
    ToolContext,
)
from .persistence.checkpoints import build_checkpoint_provider
from .prompt_loader import load_prompt
from .runtime.local import AgentRuntime
from .tools.registry import build_toolset

# Default cap on tool calls per agent run when a caller doesn't pin one via
# the run's budget. Shared with services.py's execute_deep_agent_turn, which
# reads the same fallback from AgentRun.budget_json.
DEFAULT_MAX_TOOL_CALLS = 40

# LangGraph's recursion_limit counts graph superstep transitions, not tool
# calls: each tool call is roughly two supersteps (model turn, tool turn), so
# the limit is sized at 2x the tool-call budget plus headroom for the
# framing turns (initial reasoning step, final response). Clamped to a floor
# that tolerates a couple of exchanges even at a tiny budget, and a ceiling
# that bounds worst-case run length regardless of a misconfigured budget.
_RECURSION_LIMIT_FLOOR = 8
_RECURSION_LIMIT_CEILING = 200
_RECURSION_LIMIT_PER_TOOL_CALL = 2
_RECURSION_LIMIT_HEADROOM = 4


def _recursion_limit(max_tool_calls: int) -> int:
    return max(
        _RECURSION_LIMIT_FLOOR,
        min(
            _RECURSION_LIMIT_CEILING,
            max_tool_calls * _RECURSION_LIMIT_PER_TOOL_CALL + _RECURSION_LIMIT_HEADROOM,
        ),
    )


class DeepAgentsAgentRuntime(AgentRuntime):
    """Builds one project graph through the Deep Agents factory."""

    provider = "deepagents"
    definition = AgentDefinition()

    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            from deepagents import (
                GeneralPurposeSubagentProfile,
                HarnessProfile,
                create_deep_agent,
                register_harness_profile,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned agent extra to use the Deep Agents runtime"
            ) from exc
        from .middleware import build_middleware_stack

        self._create_deep_agent: Any = create_deep_agent
        register_harness_profile(
            settings.model_provider,
            HarnessProfile(
                excluded_tools=DEFAULT_EXCLUDED_TOOLS,
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
                # extra_middleware (not middleware=... on create_deep_agent)
                # is the extension point deepagents threads into every stack
                # it assembles, including declarative subagents — see
                # ai/middleware/builder.py for why this placement matters.
                extra_middleware=build_middleware_stack,
            ),
        )

    def invoke(
        self,
        db: Any,
        ctx: Any,
        project_id: str,
        thread_key: str,
        request_text: str,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> dict[str, Any]:
        # Lazy like the deepagents import in __init__: skills_backend itself
        # imports deepagents.backends at module level, so importing it eagerly
        # would force every importer of this module (this file used to do so
        # at the top) to have the optional `agent` extra installed just to
        # import app.services/app.main, not only to actually run this method.
        from groundloom_harness.skills_backend import ReadOnlySkillBackend

        from ..integrations.ai.services import GroundloomAgentServices
        from .subagents import build_subagents

        service_factory = getattr(self, "_service_factory", GroundloomAgentServices)
        services = service_factory(db, ctx, project_id, self.settings)
        scope = ToolContext(services=services)
        toolset = build_toolset(scope)
        skill_backend = ReadOnlySkillBackend(services)
        runtime_context: AgentRuntimeContext = {
            "workspace_id": ctx.workspace_id,
            "project_id": project_id,
            "thread_id": thread_key,
            "event_sink": progress_callback,
            "cancellation_check": cancel_check,
            "tool_budget": BudgetCounter(max(1, max_tool_calls)),
        }
        model = self.settings.model_name
        if ":" not in model:
            model = f"{self.settings.model_provider}:{model}"
        checkpoint_provider = build_checkpoint_provider(self.settings)
        if checkpoint_provider is None:
            raise AgentConfigurationError(
                f"GROUNDLOOM_MODEL_PROVIDER={self.settings.model_provider!r} requires "
                "GROUNDLOOM_CHECKPOINT_BACKEND=postgres — the Deep Agents runtime persists "
                "execution state through the Postgres checkpointer and cannot run against the "
                "local checkpoint adapter. Set GROUNDLOOM_CHECKPOINT_BACKEND=postgres and "
                "configure GROUNDLOOM_DATABASE_URL (or GROUNDLOOM_WORKER_DATABASE_URL), or set "
                "GROUNDLOOM_MODEL_PROVIDER=local to keep using the deterministic adapter."
            )

        with checkpoint_provider.open() as checkpointer:
            graph: Any = self._create_deep_agent(
                model=model,
                tools=list(toolset.all_tools),
                system_prompt=load_prompt("primary_system.txt"),
                backend=skill_backend,
                skills=["/skills/project/"],
                context_schema=AgentRuntimeContext,
                checkpointer=checkpointer,
                interrupt_on={},
                name=self.definition.name,
                subagents=build_subagents(toolset, skills=["/skills/project/"]),
            )
            config = {
                "configurable": {"thread_id": thread_key},
                "recursion_limit": _recursion_limit(max_tool_calls),
            }
            graph_input = {"messages": [{"role": "user", "content": request_text}]}
            if progress_callback is None and cancel_check is None:
                return graph.invoke(graph_input, config=config, context=runtime_context)
            return consume_provider_stream(
                graph.stream(
                    graph_input,
                    config=config,
                    context=runtime_context,
                    stream_mode=["messages", "updates"],
                ),
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
