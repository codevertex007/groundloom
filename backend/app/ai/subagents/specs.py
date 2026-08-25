"""Deep Agents ``SubAgent`` specifications for bounded delegation."""

from typing import Any

from ..prompt_loader import load_prompt
from ..tools.registry import GroundloomToolset


def build_subagents(toolset: GroundloomToolset) -> list[dict[str, Any]]:
    """Build isolated specialist specs; the SDK owns task execution/state isolation."""

    return [
        {
            "name": "source-researcher",
            "description": (
                "Research selected project sources and return a bounded evidence bundle. "
                "Never mutate content or read outside the project source scope."
            ),
            "system_prompt": load_prompt("source_researcher_system.txt"),
            "tools": list(toolset.source_research),
            "interrupt_on": {},
        },
        {
            "name": "citation-auditor",
            "description": (
                "Audit current content against selected immutable passages and report "
                "unsupported or contradictory claims. Never rewrite content."
            ),
            "system_prompt": load_prompt("citation_auditor_system.txt"),
            "tools": list(toolset.citation_audit),
            "interrupt_on": {},
        },
        {
            "name": "module-writer",
            "description": (
                "Draft a bounded module from supplied evidence and propose a reviewable "
                "patch; never commit canonical content."
            ),
            "system_prompt": load_prompt("module_writer_system.txt"),
            "tools": list(toolset.module_writing),
            "interrupt_on": {},
        },
    ]
