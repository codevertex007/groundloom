"""Run the deterministic local evaluation baseline and emit JSON evidence."""

import json

from app.ai.evaluation.providers import (
    DeterministicSemanticGrader,
    RubricVersion,
    run_evaluation_cases,
)
from app.telemetry import LocalTelemetry, record_evaluation

if __name__ == "__main__":
    rubric = RubricVersion("local-grounding-v1", required_terms=("evidence", "source"))
    report = run_evaluation_cases(
        [
            ("grounded", "This answer is supported by source evidence.", ["passage-1"]),
            ("missing-citation", "This answer mentions the source but has no citation.", []),
        ],
        rubric,
        DeterministicSemanticGrader(),
    )
    telemetry = LocalTelemetry()
    record_evaluation(telemetry, report)
    report["telemetry_event"] = telemetry.records[-1]["event"]
    print(json.dumps(report, indent=2))
