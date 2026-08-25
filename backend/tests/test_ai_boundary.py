from pathlib import Path

import pytest
from app.ai.prompt_loader import load_prompt

PROMPTS = (
    "primary_system.txt",
    "source_researcher_system.txt",
    "citation_auditor_system.txt",
    "module_writer_system.txt",
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
        "ai/contracts.py",
        "ai/runtime/provider.py",
        "ai/runtime/streaming.py",
        "ai/middleware/builder.py",
        "ai/tools/registry.py",
        "ai/subagents/specs.py",
        "ai/providers/embeddings.py",
        "ai/providers/evaluation.py",
        "ai/state/checkpoints.py",
    ):
        assert (root / relative).is_file()
    for obsolete in (
        "agent_runtime.py",
        "checkpoints.py",
        "evaluation.py",
        "retrieval.py",
        "reranking.py",
        "tools/typed.py",
    ):
        assert not (root / obsolete).exists()
