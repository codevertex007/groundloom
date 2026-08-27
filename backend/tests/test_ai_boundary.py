from pathlib import Path

import pytest
from app.ai.contracts import ToolContext
from app.ai.prompt_loader import load_prompt
from app.ai.tools.registry import build_toolset
from langchain_core.tools import BaseTool

PROMPTS = (
    "primary_system.txt",
    "source_researcher_system.txt",
    "source_researcher_description.txt",
    "citation_auditor_system.txt",
    "citation_auditor_description.txt",
    "module_writer_system.txt",
    "module_writer_description.txt",
    "evaluator_system.txt",
    "skill_author_system.txt",
    "middleware_policy.txt",
)


def test_ai_prompt_assets_are_present_nonempty_and_loadable():
    for name in PROMPTS:
        prompt = load_prompt(name)
        assert len(prompt) > 20


def test_prompt_loader_rejects_unregistered_assets():
    with pytest.raises(ValueError):
        load_prompt("../../secrets.txt")


def test_ai_contribution_boundary_is_modular_and_has_no_flat_facades():
    root = Path("backend/app")
    for relative in (
        "ai/agent.py",
        "ai/contracts.py",
        "ai/skill_author.py",
        "ai/ports.py",
        "ai/common/provider_errors.py",
        "ai/runtime/factory.py",
        "ai/middleware/builder.py",
        "ai/tools/registry.py",
        "ai/tools/schemas.py",
        "ai/tools/retrieval.py",
        "ai/subagents/specs.py",
        "ai/retrieval/providers/embeddings.py",
        "ai/evaluation/providers.py",
        "ai/persistence/checkpoints.py",
        "integrations/ai/services.py",
    ):
        assert (root / relative).is_file()
    for obsolete in (
        "agent_runtime.py",
        "checkpoints.py",
        "evaluation.py",
        "retrieval.py",
        "reranking.py",
        "tools/typed.py",
        "ai/runtime/provider.py",
        "ai/runtime/streaming.py",
        "ai/state/checkpoints.py",
        "ai/tools/sources.py",
        "ai/providers/embeddings.py",
    ):
        assert not (root / obsolete).exists()


def test_reusable_harness_has_no_groundloom_dependency_and_one_composition_root():
    harness_root = Path("packages/groundloom-agent-harness/src/groundloom_harness")
    harness_python = list(harness_root.rglob("*.py"))
    assert harness_python
    assert all("from app" not in path.read_text(encoding="utf-8") for path in harness_python)

    ai_root = Path("backend/app/ai")
    composition_owners = [
        path
        for path in ai_root.rglob("*.py")
        if "create_deep_agent(" in path.read_text(encoding="utf-8")
    ]
    assert composition_owners == [ai_root / "agent.py"]
    assert all(
        "services import" not in path.read_text(encoding="utf-8")
        for path in (ai_root / "tools").glob("*.py")
    )


def test_ai_provider_adapters_do_not_reimplement_http_transport():
    ai_root = Path("backend/app/ai")
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in ai_root.rglob("*.py")
    )
    assert "import httpx" not in sources
    assert "httpx.post(" not in sources
    assert "provider_http" not in sources


def test_model_facing_tools_are_langchain_tools_with_bounded_pydantic_inputs():
    class Services:
        def __init__(self):
            self.proposal = None

        def __getattr__(self, name):
            def result(*args, **kwargs):
                if name == "propose_text_patch":
                    self.proposal = (args, kwargs)
                return [] if name in {"project_skills", "read_workspace_memory"} else {}

            return result

    services = Services()
    toolset = build_toolset(ToolContext(services=services))
    assert all(isinstance(item, BaseTool) for item in toolset.all_tools)
    assert [item.name for item in toolset.all_tools] == [
        "get_project_snapshot",
        "list_project_skills",
        "search_source_passages",
        "read_source_passage",
        "validate_current_content",
        "read_current_content",
        "propose_text_patch",
        "read_workspace_memory",
    ]

    search = next(item for item in toolset.all_tools if item.name == "search_source_passages")
    assert search.args_schema.model_json_schema()["properties"]["query"]["maxLength"] == 4_000
    assert search.invoke({"query": "authorized evidence"}) == {}
    with pytest.raises(ValueError):
        search.invoke({"query": ""})

    propose = next(item for item in toolset.all_tools if item.name == "propose_text_patch")
    propose.invoke(
        {
            "summary": "Add evidence-backed paragraph",
            "text": "Bounded draft text.",
            "citations": [
                {
                    "passage_id": "passage_block-1",
                    "source_version_id": "srcv_1",
                    "block_id": "block-1",
                    "page": 1,
                    "offsets": {"start": 0, "end": 19},
                }
            ],
        }
    )
    assert services.proposal[0][2] == [
        {
            "passage_id": "passage_block-1",
            "source_version_id": "srcv_1",
            "block_id": "block-1",
            "page": 1,
            "offsets": {"start": 0, "end": 19},
        }
    ]
