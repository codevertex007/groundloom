"""Deterministic evaluation primitives used by local gates and CI.

Semantic provider graders can implement the same protocol, but they never
replace deterministic checks for citations, scope, or required structure.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RubricVersion:
    id: str
    required_terms: tuple[str, ...] = ()
    require_citations: bool = True
    minimum_score: float = 0.75


@dataclass(frozen=True)
class Grade:
    rubric_id: str
    score: float
    verdict: str
    feedback: tuple[str, ...]


class Grader(Protocol):
    def grade(self, text: str, citations: list[str], rubric: RubricVersion) -> Grade: ...


class DeterministicSemanticGrader:
    """A transparent baseline grader for local/test execution.

    It intentionally reports a rubric result rather than pretending to be a
    model judgment. Production semantic graders may be plugged in through the
    same narrow interface and must record their pinned evaluator version.
    """

    def grade(self, text: str, citations: list[str], rubric: RubricVersion) -> Grade:
        normalized = text.casefold()
        feedback: list[str] = []
        term_score = (
            sum(term.casefold() in normalized for term in rubric.required_terms)
            / len(rubric.required_terms)
            if rubric.required_terms
            else 1.0
        )
        citation_score = 1.0 if citations or not rubric.require_citations else 0.0
        score = round((term_score + citation_score) / 2, 3)
        if term_score < 1:
            feedback.append("Required rubric terms are missing.")
        if citation_score == 0:
            feedback.append("At least one evidence citation is required.")
        verdict = "pass" if score >= rubric.minimum_score and not feedback else "needs_revision"
        return Grade(rubric.id, score, verdict, tuple(feedback))


def run_evaluation_cases(
    cases: list[tuple[str, str, list[str]]], rubric: RubricVersion, grader: Grader
) -> dict[str, object]:
    results = []
    for case_id, text, citations in cases:
        grade = grader.grade(text, citations, rubric)
        results.append(
            {
                "case_id": case_id,
                "rubric_id": grade.rubric_id,
                "score": grade.score,
                "verdict": grade.verdict,
                "feedback": list(grade.feedback),
            }
        )
    passed = sum(result["verdict"] == "pass" for result in results)
    return {
        "rubric_id": rubric.id,
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
