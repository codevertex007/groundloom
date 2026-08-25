"""Strict loader for versioned prompt assets.

Keeping prompts as package data gives AI engineers an editable, reviewable
surface without mixing prompt copy into backend orchestration code. The loader
rejects unknown or empty assets so a packaging mistake cannot silently produce
an unsafe provider request.
"""

from functools import cache
from importlib.resources import files

_PROMPT_NAMES = frozenset(
    {
        "primary_system.txt",
        "source_researcher_system.txt",
        "source_researcher_description.txt",
        "citation_auditor_system.txt",
        "citation_auditor_description.txt",
        "module_writer_system.txt",
        "module_writer_description.txt",
        "evaluator_system.txt",
        "middleware_policy.txt",
    }
)


@cache
def load_prompt(name: str) -> str:
    """Load one approved UTF-8 prompt asset by exact filename."""

    if name not in _PROMPT_NAMES:
        raise ValueError(f"Unknown Groundloom prompt asset: {name}")
    prompt = files("app.ai.prompts").joinpath(name).read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError(f"Groundloom prompt asset is empty: {name}")
    return prompt
