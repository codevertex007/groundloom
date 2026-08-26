"""Typed boundary between retrieval intelligence and product persistence."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RetrievalCandidate:
    block_id: str
    source_id: str
    source_version_id: str
    source_name: str
    block_no: int
    page: int | None
    section_path: str
    text: str
    embeddings: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class RetrievalSnapshot:
    has_source_scope: bool
    candidates: tuple[RetrievalCandidate, ...]
    semantic_scores: dict[str, float]
    backend_id: str


class RetrievalRepository(Protocol):
    def load(
        self,
        query: str,
        query_vector: list[float],
        candidate_limit: int,
    ) -> RetrievalSnapshot:
        """Return only candidates authorized by trusted application context."""
