"""Deep Agents provider runtime and factory seam."""

from typing import Any

from ...config import Settings
from ..contracts import (
    AgentDefinition,
    AgentRuntimeContext,
    CancelCheck,
    ProgressCallback,
    ToolContext,
)
from ..prompt_loader import load_prompt
from ..state.checkpoints import build_checkpoint_provider
from ..tools.registry import build_toolset
from .local import AgentRuntime
from .streaming import consume_provider_stream


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
        self._create_deep_agent = create_deep_agent
        register_harness_profile(
            settings.model_provider,
            HarnessProfile(
                excluded_tools=frozenset(
                    {
                        "ls",
                        "read_file",
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
        from ..middleware import build_middleware_stack
        from ..subagents import build_subagents

        scope = ToolContext(
            db=db,
            runtime_context=ctx,
            project_id=project_id,
            settings=self.settings,
        )
        toolset = build_toolset(scope)
        runtime_context: AgentRuntimeContext = {
            "workspace_id": ctx.workspace_id,
            "project_id": project_id,
            "thread_key": thread_key,
            "settings": self.settings,
            "progress_callback": progress_callback,
            "cancel_check": cancel_check,
            "max_tool_calls": max(1, max_tool_calls),
            "tool_calls_used": 0,
        }
        model = self.settings.model_name
        if ":" not in model:
            model = f"{self.settings.model_provider}:{model}"
        checkpoint_provider = build_checkpoint_provider(self.settings)
        if checkpoint_provider is None:
            raise RuntimeError("The Deep Agents runtime requires the Postgres checkpoint backend")

        with checkpoint_provider.open() as checkpointer:
            graph = self._create_deep_agent(
                model=model,
                tools=list(toolset.all_tools),
                system_prompt=load_prompt("primary_system.txt"),
                middleware=build_middleware_stack(),
                context_schema=AgentRuntimeContext,
                checkpointer=checkpointer,
                interrupt_on={},
                name=self.definition.name,
                subagents=build_subagents(toolset),
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
