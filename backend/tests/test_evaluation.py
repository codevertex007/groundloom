import json

import httpx
import pytest
from app.config import Settings
from app.errors import GroundloomError
from app.evaluation import (
    DeterministicSemanticGrader,
    OpenAICompatibleSemanticGrader,
    RubricVersion,
    build_grader,
    run_evaluation_cases,
)
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

    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "score": 0.87,
                                    "verdict": "pass",
                                    "feedback": ["Evidence is sufficient."],
                                }
                            )
                        }
                    }
                ]
            }

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    grader = OpenAICompatibleSemanticGrader(
        api_key="secret-do-not-log",
        base_url="https://grader.example/v1",
        model="grader-test",
    )
    grade = grader.grade(
        "Grounded evidence text", ["passage_1"], RubricVersion("rubric-v1")
    )
    assert grade.score == 0.87
    assert grade.verdict == "pass"
    assert calls[0][0] == "https://grader.example/v1/chat/completions"
    assert calls[0][1]["json"]["response_format"] == {"type": "json_object"}

    class BadResponse(Response):
        def json(self):
            return {"choices": [{"message": {"content": '{"score": 2}'}}]}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: BadResponse())
    with pytest.raises(GroundloomError) as invalid:
        grader.grade("text", [], RubricVersion("rubric-v1"))
    assert invalid.value.code == "PROVIDER_INVALID_RESPONSE"


def test_semantic_grader_outage_and_missing_configuration_are_typed(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("secret")))
    grader = OpenAICompatibleSemanticGrader(
        api_key="secret-do-not-log",
        base_url="https://grader.example/v1",
        model="grader-test",
    )
    with pytest.raises(GroundloomError) as outage:
        grader.grade("text", [], RubricVersion("rubric-v1"))
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True

    with pytest.raises(GroundloomError) as missing:
        build_grader(Settings(evaluator_provider="openai"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"
