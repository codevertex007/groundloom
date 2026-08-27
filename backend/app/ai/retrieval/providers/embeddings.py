"""Embedding and hybrid-retrieval provider boundaries.

The product owns authorization, source-version filtering, and citation lineage.
This module only supplies derived vectors and bounded similarity calculations.
The local provider is deterministic and credential-free; the HTTP provider is
intentionally narrow and never exposes provider response bodies or credentials
through product errors.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Protocol, cast

from pydantic import SecretStr

from ....config import Settings
from ....errors import GroundloomError
from ...common import raise_provider_error


class EmbeddingProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one finite, fixed-dimension vector per input text."""


class EmbeddingClient(Protocol):
    """The LangChain embeddings surface consumed by this adapter."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


def _validate_vectors(vectors: list[list[float]], expected: int) -> list[list[float]]:
    if len(vectors) == 0:
        return []
    if any(len(vector) != expected for vector in vectors):
        raise GroundloomError(
            "PROVIDER_INVALID_RESPONSE",
            "The embedding provider returned an incompatible vector dimension.",
            502,
        )
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise GroundloomError(
            "PROVIDER_INVALID_RESPONSE",
            "The embedding provider returned a non-finite vector.",
            502,
        )
    return vectors


@dataclass(frozen=True)
class DeterministicEmbeddingProvider:
    dimensions: int = 32
    provider_id: str = "local-hash"
    model: str = "deterministic-hash-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for term in re.findall(r"[a-z0-9]{2,}", text.lower()):
                digest = hashlib.sha256(f"{self.model}:{term}".encode()).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector] if norm else vector)
        return _validate_vectors(vectors, self.dimensions)


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    """LangChain-backed OpenAI-compatible embedding adapter."""

    api_key: str
    base_url: str
    model: str
    dimensions: int
    timeout_seconds: float = 10.0
    max_retries: int = 2
    provider_id: str = "openai-compatible"
    client: EmbeddingClient | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.client is not None:
            return
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned agent extra to use OpenAI-compatible embeddings"
            ) from exc
        object.__setattr__(
            self,
            "client",
            OpenAIEmbeddings(
                api_key=SecretStr(self.api_key),
                base_url=self.base_url.rstrip("/"),
                model=self.model,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
                check_embedding_ctx_length=False,
            ),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            raw_vectors = cast(EmbeddingClient, self.client).embed_documents(texts)
        except Exception as exc:
            raise_provider_error("embedding provider", exc)
        try:
            vectors = [list(map(float, vector)) for vector in raw_vectors]
        except (TypeError, ValueError) as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The embedding provider returned an invalid response.",
                502,
            ) from exc
        if len(vectors) != len(texts):
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The embedding provider returned an incomplete response.",
                502,
            )
        return _validate_vectors(vectors, self.dimensions)


def build_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or Settings()
    provider = settings.embedding_provider.lower()
    if provider in {"local", "deterministic"}:
        return DeterministicEmbeddingProvider(dimensions=settings.embedding_dimensions)
    if provider in {"openai", "openai-compatible"}:
        if not settings.embedding_api_key:
            raise GroundloomError(
                "PROVIDER_MISCONFIGURED",
                "The configured embedding provider has no API key.",
                503,
            )
        return OpenAICompatibleEmbeddingProvider(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url or "https://api.openai.com/v1",
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=max(0, settings.agent_max_attempts - 1),
        )
    raise GroundloomError(
        "PROVIDER_MISCONFIGURED",
        "The configured embedding provider is unsupported.",
        503,
    )


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True)) / denominator))


def hybrid_score(lexical_score: float, semantic_score: float) -> float:
    """Combine bounded lexical and semantic scores deterministically."""
    return max(0.0, min(1.0, 0.65 * lexical_score + 0.35 * max(0.0, semantic_score)))
