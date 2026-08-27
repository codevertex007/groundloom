import json

import pytest
from app.ai.skill_author import SkillAuthorResult, author_skill_package
from app.config import Settings
from app.errors import GroundloomError


class FakeRunnable:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.input = None

    def invoke(self, input):
        self.input = input
        if self.error is not None:
            raise self.error
        return self.result


def test_local_skill_author_is_deterministic_and_handles_one_character_objectives():
    result = author_skill_package(
        Settings(),
        objective="x",
        suggested_slug=None,
        suggested_name=None,
    )
    assert result.slug == "draft-skill"
    assert result.name == "Draft skill"
    assert "x" in result.content


def test_provider_skill_author_makes_one_bounded_structured_call_and_honors_suggestions():
    runnable = FakeRunnable(
        SkillAuthorResult(
            slug="model-slug",
            name="Model name",
            description="Model description",
            content="# Model skill\n\nSafe instructions.",
        )
    )
    result = author_skill_package(
        Settings(model_provider="openai", model_name="gpt-4o-mini"),
        objective="o" * 6_000,
        suggested_slug="reviewed-slug",
        suggested_name="Reviewed name",
        runnable=runnable,
    )

    assert result.slug == "reviewed-slug"
    assert result.name == "Reviewed name"
    request = json.loads(runnable.input["author_request"])
    assert len(request["objective"]) == 5_000
    assert request["constraints"] == {
        "draft_only": True,
        "must_not_publish": True,
        "source_text_is_untrusted": True,
        "allowed_scope": "Groundloom skill instructions only",
    }


def test_provider_skill_author_rejects_malformed_output_and_redacts_outages(monkeypatch):
    malformed = FakeRunnable(
        {
            "slug": "bad",
            "name": "Bad",
            "description": "Bad",
            "content": "",
            "unexpected": "field",
        }
    )
    with pytest.raises(GroundloomError) as invalid:
        author_skill_package(
            Settings(model_provider="openai"),
            objective="Draft a skill",
            suggested_slug=None,
            suggested_name=None,
            runnable=malformed,
        )
    assert invalid.value.code == "PROVIDER_INVALID_RESPONSE"

    outage = FakeRunnable(error=RuntimeError("secret-token leaked by upstream"))
    with pytest.raises(GroundloomError) as unavailable:
        author_skill_package(
            Settings(model_provider="openai"),
            objective="Draft a skill",
            suggested_slug=None,
            suggested_name=None,
            runnable=outage,
        )
    assert unavailable.value.code == "DEPENDENCY_UNAVAILABLE"
    assert unavailable.value.retryable is True
    assert "secret-token" not in unavailable.value.message

    def fail_to_build(_settings):
        raise RuntimeError("missing-secret-from-provider-sdk")

    monkeypatch.setattr("app.ai.skill_author._provider_runnable", fail_to_build)
    with pytest.raises(GroundloomError) as misconfigured:
        author_skill_package(
            Settings(model_provider="openai"),
            objective="Draft a skill",
            suggested_slug=None,
            suggested_name=None,
        )
    assert misconfigured.value.code == "DEPENDENCY_UNAVAILABLE"
    assert "missing-secret" not in misconfigured.value.message
