"""Deterministic and provider-backed evaluation primitives used by quality gates.

Semantic provider graders can implement the same protocol, but they never
replace deterministic checks for citations, scope, or required structure.
"""

import json
import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .errors import GroundloomError


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

    provider_id = "local-deterministic"
    model = "deterministic-rubric-v1"

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


@dataclass(frozen=True)
class OpenAICompatibleSemanticGrader:
    """Narrow structured-output evaluator adapter.

    The provider sees bounded draft text, citation IDs, and rubric metadata;
    Groundloom still owns deterministic citation/structure invariants.
    """

    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 20.0
    provider_id: str = "openai-compatible"

    def grade(self, text: str, citations: list[str], rubric: RubricVersion) -> Grade:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        prompt = {
            "rubric_id": rubric.id,
            "required_terms": list(rubric.required_terms),
            "require_citations": rubric.require_citations,
            "minimum_score": rubric.minimum_score,
            "text": text[:20_000],
            "citations": citations[:100],
        }
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return JSON only with score (0..1), verdict "
                                "(pass or needs_revision), and feedback (array of short strings)."
                            ),
                        },
                        {"role": "user", "content": json.dumps(prompt, separators=(",", ":"))},
                    ],
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The semantic evaluator is temporarily unavailable.",
                503,
                retryable=True,
            ) from exc
        if response.status_code >= 500:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The semantic evaluator is temporarily unavailable.",
                503,
                retryable=True,
            )
        if response.status_code >= 400:
            raise GroundloomError(
                "PROVIDER_REJECTED",
                "The semantic evaluator rejected the request.",
                422,
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content) if isinstance(content, str) else content
            score = float(result["score"])
            verdict = str(result["verdict"])
            feedback = result.get("feedback", [])
            if (
                not math.isfinite(score)
                or not 0.0 <= score <= 1.0
                or verdict not in {"pass", "needs_revision"}
                or not isinstance(feedback, list)
                or len(feedback) > 20
                or any(not isinstance(item, str) or len(item) > 500 for item in feedback)
            ):
                raise ValueError("invalid evaluator result")
        except (AttributeError, IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The semantic evaluator returned an invalid result.",
                502,
            ) from exc
        return Grade(rubric.id, round(score, 3), verdict, tuple(feedback))


def build_grader(settings: Settings | None = None) -> Grader:
    settings = settings or Settings()
    provider = settings.evaluator_provider.lower()
    if provider in {"local", "deterministic"}:
        return DeterministicSemanticGrader()
    if provider in {"openai", "openai-compatible"}:
        if not settings.evaluator_api_key:
            raise GroundloomError(
                "PROVIDER_MISCONFIGURED",
                "The configured semantic evaluator has no API key.",
                503,
            )
        return OpenAICompatibleSemanticGrader(
            api_key=settings.evaluator_api_key,
            base_url=settings.evaluator_base_url or "https://api.openai.com/v1",
            model=settings.evaluator_model,
            timeout_seconds=settings.evaluator_timeout_seconds,
        )
    raise GroundloomError(
        "PROVIDER_MISCONFIGURED",
        "The configured semantic evaluator is unsupported.",
        503,
    )


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
