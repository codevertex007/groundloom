"""Deterministic and provider-backed evaluation primitives used by quality gates.

Semantic provider graders can implement the same protocol, but they never
replace deterministic checks for citations, scope, or required structure.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from ...config import Settings
from ...errors import GroundloomError
from ..common import raise_provider_error
from ..prompt_loader import load_prompt


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


class SemanticGradeResult(BaseModel):
    """Provider output validated before it crosses into product evaluation state."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    verdict: Literal["pass", "needs_revision"]
    feedback: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("feedback")
    @classmethod
    def feedback_is_bounded(cls, value: list[str]) -> list[str]:
        if any(len(item) > 500 for item in value):
            raise ValueError("feedback items must be at most 500 characters")
        return value


class StructuredGradeRunnable(Protocol):
    def invoke(self, input: dict[str, Any]) -> Any: ...


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
    """LangChain structured-output evaluator adapter.

    The provider sees bounded draft text, citation IDs, and rubric metadata;
    Groundloom still owns deterministic citation/structure invariants.
    """

    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 20.0
    max_retries: int = 2
    provider_id: str = "openai-compatible"
    runnable: StructuredGradeRunnable | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.runnable is not None:
            return
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned agent extra to use the semantic evaluator"
            ) from exc
        model = ChatOpenAI(
            api_key=SecretStr(self.api_key),
            base_url=self.base_url.rstrip("/"),
            model=self.model,
            temperature=0,
            timeout=self.timeout_seconds,
            max_retries=self.max_retries,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("evaluator_system.txt")),
                (
                    "human",
                    "Evaluate only the bounded input below and return the requested JSON object.\n\n"
                    "{evaluation_input}",
                ),
            ]
        )
        object.__setattr__(
            self,
            "runnable",
            prompt | model.with_structured_output(SemanticGradeResult, method="json_mode"),
        )

    def grade(self, text: str, citations: list[str], rubric: RubricVersion) -> Grade:
        evaluation_input = {
            "rubric_id": rubric.id,
            "required_terms": list(rubric.required_terms),
            "require_citations": rubric.require_citations,
            "minimum_score": rubric.minimum_score,
            "text": text[:20_000],
            "citations": citations[:100],
        }
        try:
            raw_result = cast(StructuredGradeRunnable, self.runnable).invoke(
                {"evaluation_input": json.dumps(evaluation_input, separators=(",", ":"))}
            )
        except (OutputParserException, ValidationError, TypeError, ValueError) as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The semantic evaluator returned an invalid result.",
                502,
            ) from exc
        except Exception as exc:
            raise_provider_error("semantic evaluator", exc)
        try:
            result = SemanticGradeResult.model_validate(raw_result)
        except ValidationError as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The semantic evaluator returned an invalid result.",
                502,
            ) from exc
        return Grade(
            rubric.id,
            round(result.score, 3),
            result.verdict,
            tuple(result.feedback),
        )


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
            max_retries=max(0, settings.agent_max_attempts - 1),
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
