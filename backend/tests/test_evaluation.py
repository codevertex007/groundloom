import pytest
from app.ai.evaluation.providers import (
    DeterministicSemanticGrader,
    OpenAICompatibleSemanticGrader,
    RubricVersion,
    build_grader,
    run_evaluation_cases,
)
from app.config import Settings
from app.errors import GroundloomError
from app.telemetry import LocalTelemetry, record_evaluation


def test_deterministic_rubric_requires_terms_and_citations():
    rubric = RubricVersion("rubric-v1", required_terms=("grounded", "evidence"))
    report = run_evaluation_cases(
        [
            ("pass", "A grounded answer uses evidence.", ["passage-1"]),
            ("fail", "An unsupported answer.", []),
        ],
        rubric,
        DeterministicSemanticGrader(),
    )
    assert report["case_count"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["results"][1]["verdict"] == "needs_revision"


def test_evaluation_observation_uses_redacted_telemetry():
    telemetry = LocalTelemetry()
    record_evaluation(telemetry, {"rubric_id": "v1", "prompt": "private", "passed": 1})
    assert telemetry.records[-1]["event"] == "evaluation.completed"
    assert telemetry.records[-1]["attributes"]["prompt"] == "[REDACTED]"


def test_openai_compatible_semantic_grader_validates_structured_output(monkeypatch):
    calls = []

    class Runnable:
        def invoke(self, input):
            calls.append(input)
            return {
                "score": 0.87,
                "verdict": "pass",
                "feedback": ["Evidence is sufficient."],
            }

    grader = OpenAICompatibleSemanticGrader(
        api_key="secret-do-not-log",
        base_url="https://grader.example/v1",
        model="grader-test",
        runnable=Runnable(),
    )
    grade = grader.grade("Grounded evidence text", ["passage_1"], RubricVersion("rubric-v1"))
    assert grade.score == 0.87
    assert grade.verdict == "pass"
    assert "Grounded evidence text" in calls[0]["evaluation_input"]

    class BadRunnable:
        def invoke(self, _input):
            return {"score": 2, "verdict": "pass", "feedback": []}

    bad_grader = OpenAICompatibleSemanticGrader(
        api_key="secret-do-not-log",
        base_url="https://grader.example/v1",
        model="grader-test",
        runnable=BadRunnable(),
    )
    with pytest.raises(GroundloomError) as invalid:
        bad_grader.grade("text", [], RubricVersion("rubric-v1"))
    assert invalid.value.code == "PROVIDER_INVALID_RESPONSE"


def test_semantic_grader_outage_and_missing_configuration_are_typed():
    class UnavailableRunnable:
        def invoke(self, _input):
            raise RuntimeError("secret")

    grader = OpenAICompatibleSemanticGrader(
        api_key="secret-do-not-log",
        base_url="https://grader.example/v1",
        model="grader-test",
        runnable=UnavailableRunnable(),
    )
    with pytest.raises(GroundloomError) as outage:
        grader.grade("text", [], RubricVersion("rubric-v1"))
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True

    with pytest.raises(GroundloomError) as missing:
        build_grader(Settings(evaluator_provider="openai"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"
