from pathlib import Path

import pytest
from app.ai.prompt_loader import load_prompt

PROMPTS = (
    "primary_system.txt",
    "source_researcher_system.txt",
    "source_researcher_description.txt",
    "citation_auditor_system.txt",
    "citation_auditor_description.txt",
    "module_writer_system.txt",
    "module_writer_description.txt",
    "evaluator_system.txt",
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
        "ai/ports.py",
        "ai/common/provider_http.py",
        "ai/runtime/factory.py",
        "ai/middleware/builder.py",
        "ai/tools/registry.py",
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
