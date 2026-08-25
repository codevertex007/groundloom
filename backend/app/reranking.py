"""Bounded reranker adapters for retrieval candidates.

The local reranker is deterministic and credential-free. The optional HTTP
adapter follows the Cohere-compatible `/rerank` response shape without making
provider-specific objects part of Groundloom's product contracts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .errors import GroundloomError


class Reranker(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model(self) -> str: ...

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Return one bounded relevance score per input document."""


def _terms(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]{3,}", value.lower())


@dataclass(frozen=True)
class DeterministicReranker:
    provider_id: str = "local-overlap"
    model: str = "deterministic-overlap-v1"

    def score(self, query: str, documents: list[str]) -> list[float]:
        query_terms = _terms(query)
        query_set = set(query_terms)
        phrase = " ".join(query_terms)
        scores: list[float] = []
        for document in documents:
            normalized = " ".join(document.lower().split())
            document_set = set(_terms(document))
            overlap = len(query_set.intersection(document_set)) / max(len(query_set), 1)
            exact_phrase = 1.0 if phrase and phrase in normalized else 0.0
            scores.append(max(0.0, min(1.0, 0.8 * overlap + 0.2 * exact_phrase)))
        return scores


@dataclass(frozen=True)
class CohereCompatibleReranker:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 10.0
    provider_id: str = "cohere-compatible"

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/rerank"):
            endpoint = f"{endpoint}/rerank"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                    "return_documents": False,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The reranker is temporarily unavailable.",
                503,
                retryable=True,
            ) from exc
        if response.status_code >= 500:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The reranker is temporarily unavailable.",
                503,
                retryable=True,
            )
        if response.status_code >= 400:
            raise GroundloomError(
                "PROVIDER_REJECTED",
                "The reranker rejected the request.",
                422,
            )
        scores = [0.0] * len(documents)
        try:
            records = response.json().get("results", [])
            seen: set[int] = set()
            for record in records:
                index = int(record["index"])
                score = float(record["relevance_score"])
                if index < 0 or index >= len(documents) or index in seen or not math.isfinite(score):
                    raise ValueError("invalid reranker result")
                seen.add(index)
                scores[index] = max(0.0, min(1.0, score))
            if len(seen) != len(documents):
                raise ValueError("incomplete reranker result")
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The reranker returned an invalid response.",
                502,
            ) from exc
        return scores


def build_reranker(settings: Settings | None = None) -> Reranker:
    settings = settings or Settings()
    provider = settings.reranker_provider.lower()
    if provider in {"local", "deterministic"}:
        return DeterministicReranker(model=settings.reranker_model)
    if provider in {"cohere", "cohere-compatible"}:
        if not settings.reranker_api_key:
            raise GroundloomError(
                "PROVIDER_MISCONFIGURED",
                "The configured reranker has no API key.",
                503,
            )
        return CohereCompatibleReranker(
            api_key=settings.reranker_api_key,
            base_url=settings.reranker_base_url or "https://api.cohere.com/v1",
            model=settings.reranker_model,
            timeout_seconds=settings.reranker_timeout_seconds,
        )
    raise GroundloomError(
        "PROVIDER_MISCONFIGURED",
        "The configured reranker is unsupported.",
        503,
    )


def combine_rerank_scores(base_score: float, rerank_score: float) -> float:
    """Blend bounded candidate and reranker scores without changing rank bounds."""
    return max(0.0, min(1.0, 0.7 * max(0.0, min(1.0, base_score)) + 0.3 * rerank_score))
