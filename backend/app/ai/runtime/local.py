"""Credential-free deterministic runtime used by local execution and tests."""

from typing import Any

from ..contracts import AgentDefinition, CancelCheck, ProgressCallback


class AgentRuntime:
    definition = AgentDefinition()

    def capabilities(self) -> dict[str, Any]:
        return {
            "adaptive_loop": True,
            "persistent_thread": True,
            "planning": True,
            "typed_tools": True,
            "dynamic_delegation": True,
            "canonical_commit": False,
            "unrestricted_shell": False,
            "scope_from_model": False,
        }

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
        raise RuntimeError(f"The {self.__class__.__name__} runtime does not support provider invocation")


class LocalDeterministicAgentRuntime(AgentRuntime):
    """Safe local/test runtime used when no model credentials are configured."""

    provider = "local"
