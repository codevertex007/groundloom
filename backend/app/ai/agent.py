"""Groundloom's single Deep Agents composition root.

This module owns model, prompt, tool, middleware, skill, subagent, checkpoint,
and streaming composition. Reusable policy primitives live in
``groundloom_harness``; backend capabilities arrive through a typed adapter.
"""

from typing import Any

from groundloom_harness import BudgetCounter
from groundloom_harness.skills_backend import ReadOnlySkillBackend
from groundloom_harness.streaming import consume_provider_stream

from ..config import Settings
from .contracts import (
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


class DeepAgentsAgentRuntime(AgentRuntime):
    """Builds one project graph through the Deep Agents factory."""

    provider = "deepagents"
    definition = AgentDefinition()

    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned agent extra to use the Deep Agents runtime"
            ) from exc
        self._create_deep_agent: Any = create_deep_agent
        register_harness_profile(
            settings.model_provider,
            HarnessProfile(
                excluded_tools=frozenset(
                    {
                        "write_file",
                        "edit_file",
                        "delete",
                        "glob",
                        "grep",
                        "execute",
                    }
                )
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
        max_tool_calls: int = 40,
    ) -> dict[str, Any]:
        from ..integrations.ai.services import GroundloomAgentServices
        from .middleware import build_middleware_stack
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
            raise RuntimeError("The Deep Agents runtime requires the Postgres checkpoint backend")

        with checkpoint_provider.open() as checkpointer:
            graph: Any = self._create_deep_agent(
                model=model,
                tools=list(toolset.all_tools),
                system_prompt=load_prompt("primary_system.txt"),
                middleware=build_middleware_stack(),
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
                "recursion_limit": max(8, min(200, max_tool_calls * 2 + 4)),
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
