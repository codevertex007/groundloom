"""Bounded reranker adapters for retrieval candidates.

The local reranker is deterministic and credential-free. The optional Cohere
adapter delegates provider transport and response handling to LangChain while
keeping provider objects outside Groundloom's product contracts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from langchain_core.documents import Document

from ....config import Settings
from ....errors import GroundloomError
from ...common import raise_provider_error


class Reranker(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model(self) -> str: ...

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Return one bounded relevance score per input document."""


class DocumentReranker(Protocol):
    """The LangChain document-compressor surface consumed by this adapter."""

    def compress_documents(
        self,
        documents: list[Document],
        query: str,
    ) -> Any: ...


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
    """LangChain-backed Cohere v2 reranker."""

    api_key: str
    base_url: str
    model: str
    timeout_seconds: float = 10.0
    provider_id: str = "cohere"
    reranker: DocumentReranker | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.reranker is not None:
            return
        try:
            import cohere
            from langchain_cohere import CohereRerank
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned agent extra to use Cohere reranking"
            ) from exc
        client = cohere.ClientV2(
            api_key=self.api_key,
            base_url=self.base_url.rstrip("/"),
            timeout=self.timeout_seconds,
            client_name="groundloom-langchain",
        )
        object.__setattr__(
            self,
            "reranker",
            CohereRerank(client=client, model=self.model, top_n=None),
        )

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        source_documents = [
            Document(page_content=text, metadata={"groundloom_index": index})
            for index, text in enumerate(documents)
        ]
        try:
            ranked = cast(DocumentReranker, self.reranker).compress_documents(
                source_documents,
                query,
            )
        except Exception as exc:
            raise_provider_error("reranker", exc)
        scores = [0.0] * len(documents)
        try:
            seen: set[int] = set()
            for document in ranked:
                index = int(document.metadata["groundloom_index"])
                score = float(document.metadata["relevance_score"])
                if (
                    index < 0
                    or index >= len(documents)
                    or index in seen
                    or not math.isfinite(score)
                ):
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
            base_url=settings.reranker_base_url or "https://api.cohere.com",
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
