from app.evaluation import DeterministicSemanticGrader, RubricVersion, run_evaluation_cases


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
