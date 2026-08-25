"""Compatibility facade for AI retrieval providers."""

from .ai.retrieval import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    build_embedding_provider,
    cosine_similarity,
    hybrid_score,
)

__all__ = [
    "DeterministicEmbeddingProvider",
    "EmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "build_embedding_provider",
    "cosine_similarity",
    "hybrid_score",
]
