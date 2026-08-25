"""Stable AI tool contracts used for traceability and policy review."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolContract:
    tool_id: str
    name: str
    mode: str
    max_result_items: int


TOOL_CATALOG = {
    contract.tool_id: contract
    for contract in (
        ToolContract("TOOL-PROJ-001", "get_project_snapshot", "read", 1),
        ToolContract("TOOL-PROJ-002", "list_project_skills", "read", 100),
        ToolContract("TOOL-RET-001", "search_source_passages", "read", 8),
        ToolContract("TOOL-RET-002", "read_source_passage", "read", 1),
        ToolContract("TOOL-CONT-001", "read_current_content", "read", 100),
        ToolContract("TOOL-CONT-002", "validate_current_content", "read", 100),
        ToolContract("TOOL-CONT-003", "propose_text_patch", "proposal", 1),
        ToolContract("TOOL-MEM-001", "read_workspace_memory", "read", 100),
    )
}
