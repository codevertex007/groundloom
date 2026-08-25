from concurrent.futures import ThreadPoolExecutor

import pytest
from groundloom_harness import BudgetCounter, BudgetExceeded, ToolPolicy
from groundloom_harness.skills_backend import ReadOnlySkillBackend, SkillPackage


class StaticSkillSource:
    def list_packages(self):
        return (
            SkillPackage(
                "source-grounded-writing",
                "---\nname: source-grounded-writing\ndescription: Cite evidence.\n---\n\n# Rules",
                {"references/checklist.txt": "Check every factual claim."},
            ),
        )


def test_budget_counter_is_safe_under_parallel_tool_calls():
    counter = BudgetCounter(8)

    def consume_once(_index):
        try:
            return counter.consume()
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(consume_once, range(20)))

    assert len([value for value in results if value is not None]) == 8
    assert counter.used == 8


def test_tool_policy_keeps_skill_reads_and_denies_mutating_or_execution_tools():
    class Tool:
        def __init__(self, name):
            self.name = name

    visible = ToolPolicy().visible(
        [Tool("read_file"), Tool("ls"), Tool("write_file"), Tool("execute"), Tool("search")]
    )
    assert [tool.name for tool in visible] == ["read_file", "ls", "search"]


def test_skill_backend_is_bounded_read_only_and_supports_deepagents_discovery():
    backend = ReadOnlySkillBackend(StaticSkillSource())
    listing = backend.ls("/skills/project/")
    assert listing.error is None
    assert [entry["path"] for entry in listing.entries] == [
        "/skills/project/source-grounded-writing"
    ]

    read = backend.read("/skills/project/source-grounded-writing/SKILL.md")
    assert read.error is None
    assert "name: source-grounded-writing" in read.file_data["content"]
    assert backend.read("/etc/passwd").error == "permission_denied"
    assert backend.write("/skills/project/new.txt", "no").error == "permission_denied"

    downloaded = backend.download_files(
        ["/skills/project/source-grounded-writing/SKILL.md"]
    )
    assert downloaded[0].error is None
    assert downloaded[0].content.startswith(b"---")


def test_skill_packages_reject_traversal_and_invalid_slugs():
    with pytest.raises(ValueError):
        SkillPackage("bad_slug", "content").files()
    with pytest.raises(ValueError):
        SkillPackage("valid", "content", {"../secret.txt": "no"}).files()
