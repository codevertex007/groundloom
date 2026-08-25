"""Deep Agents ``SubAgent`` specifications for bounded delegation."""

from deepagents import SubAgent

from ..prompt_loader import load_prompt
from ..tools.registry import GroundloomToolset


def build_subagents(
    toolset: GroundloomToolset,
    *,
    skills: list[str],
) -> list[SubAgent]:
    """Build isolated specialist specs; the SDK owns task execution/state isolation."""

    return [
        {
            "name": "source-researcher",
            "description": load_prompt("source_researcher_description.txt"),
            "system_prompt": load_prompt("source_researcher_system.txt"),
            "tools": list(toolset.source_research),
            "skills": skills,
            "interrupt_on": {},
        },
        {
            "name": "citation-auditor",
            "description": load_prompt("citation_auditor_description.txt"),
            "system_prompt": load_prompt("citation_auditor_system.txt"),
            "tools": list(toolset.citation_audit),
            "skills": skills,
            "interrupt_on": {},
        },
        {
            "name": "module-writer",
            "description": load_prompt("module_writer_description.txt"),
            "system_prompt": load_prompt("module_writer_system.txt"),
            "tools": list(toolset.module_writing),
            "skills": skills,
            "interrupt_on": {},
        },
    ]
