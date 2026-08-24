from app.evaluation import DeterministicSemanticGrader, RubricVersion, run_evaluation_cases
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
