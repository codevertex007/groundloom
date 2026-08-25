from pathlib import Path

import pytest
from app.ai.prompt_loader import load_prompt

PROMPTS = (
    "primary_system.txt",
    "source_researcher_system.txt",
    "citation_auditor_system.txt",
    "module_writer_system.txt",
    "evaluator_system.txt",
)


def test_ai_prompt_assets_are_present_nonempty_and_loadable():
    for name in PROMPTS:
        prompt = load_prompt(name)
        assert prompt
        assert len(prompt) > 20


def test_prompt_loader_rejects_unregistered_assets():
    with pytest.raises(ValueError):
        load_prompt("../../secrets.txt")


def test_backend_runtime_facade_contains_no_prompt_instructions():
    facade = Path("backend/app/agent_runtime.py").read_text(encoding="utf-8")
    assert "You are Groundloom" not in facade
    assert "app.ai.agent_runtime" in facade
