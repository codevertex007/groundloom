"""Bounded hybrid retrieval used by the HTTP API and retrieval agent tool."""

import re

from ...schemas import EvidenceBundle, PassageOut
from .contracts import RetrievalCandidate, RetrievalRepository
from .providers.embeddings import EmbeddingProvider, cosine_similarity, hybrid_score
from .providers.reranking import Reranker, combine_rerank_scores


class RetrievalService:
    def __init__(
        self,
        repository: RetrievalRepository,
        embeddings: EmbeddingProvider,
        reranker: Reranker,
    ):
        self.repository = repository
        self.embeddings = embeddings
        self.reranker = reranker

    def search(self, query: str, limit: int = 8) -> EvidenceBundle:
        limit = max(1, min(limit, 100))
        query_vector = self.embeddings.embed([query])[0]
        candidate_limit = max(16, min(100, limit * 8))
        snapshot = self.repository.load(query_vector, candidate_limit)
        if not snapshot.has_source_scope:
            return EvidenceBundle(
                query=query,
                retrieval_version=self._version(snapshot.backend_id),
                passages=[],
                gaps=["No selected source versions are available."],
            )

        terms = [term.lower() for term in re.findall(r"[\w-]{3,}", query)]
        ranked: list[tuple[float, RetrievalCandidate]] = []
        for candidate in snapshot.candidates:
            normalized = candidate.text.lower()
            lexical = sum(1 for term in terms if term in normalized) / max(len(terms), 1)
            raw_semantic = snapshot.semantic_scores.get(candidate.block_id)
            if raw_semantic is None:
                raw_semantic = cosine_similarity(query_vector, candidate.embedding)
            score = hybrid_score(lexical, max(0.0, raw_semantic))
            if score > 0 and (lexical > 0 or raw_semantic >= 0.25):
                ranked.append((score, candidate))

        ranked.sort(key=self._rank_key)
        rerank_candidates = ranked[:candidate_limit]
        if rerank_candidates:
            scores = self.reranker.score(
                query, [candidate.text[:5000] for _, candidate in rerank_candidates]
            )
            ranked = [
                (combine_rerank_scores(base, scores[index]), candidate)
                for index, (base, candidate) in enumerate(rerank_candidates)
            ]
            ranked = self._expand_neighbors(ranked, snapshot.candidates, limit)

        ranked.sort(key=self._rank_key)
        deduped: list[tuple[float, RetrievalCandidate]] = []
        seen: set[tuple[str, str]] = set()
        for score, candidate in ranked:
            key = (
                candidate.source_version_id,
                re.sub(r"\s+", " ", candidate.text).strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append((score, candidate))

        passages = [self._passage(score, candidate) for score, candidate in deduped[:limit]]
        return EvidenceBundle(
            query=query,
            retrieval_version=self._version(snapshot.backend_id),
            passages=passages,
            gaps=[] if passages else ["No selected passage matched the request."],
        )

    @staticmethod
    def _rank_key(item: tuple[float, RetrievalCandidate]) -> tuple[float, str, int, str]:
        score, candidate = item
        return (-score, candidate.source_version_id, candidate.block_no, candidate.block_id)

    @staticmethod
    def _expand_neighbors(
        ranked: list[tuple[float, RetrievalCandidate]],
        candidates: tuple[RetrievalCandidate, ...],
        limit: int,
    ) -> list[tuple[float, RetrievalCandidate]]:
        by_version: dict[str, list[RetrievalCandidate]] = {}
        for candidate in candidates:
            by_version.setdefault(candidate.source_version_id, []).append(candidate)
        for blocks in by_version.values():
            blocks.sort(key=lambda item: (item.block_no, item.block_id))
        ranked_ids = {candidate.block_id for _, candidate in ranked}
        for base_score, candidate in ranked[: min(limit, 8)]:
            if base_score < 0.35:
                continue
            blocks = by_version.get(candidate.source_version_id, [])
            position = next(
                (index for index, item in enumerate(blocks) if item.block_id == candidate.block_id),
                None,
            )
            if position is None:
                continue
            for neighbor_position in (position - 1, position + 1):
                if 0 <= neighbor_position < len(blocks):
                    neighbor = blocks[neighbor_position]
                    if neighbor.block_id not in ranked_ids:
                        ranked.append((base_score * 0.55, neighbor))
                        ranked_ids.add(neighbor.block_id)
        return ranked

    @staticmethod
    def _passage(score: float, candidate: RetrievalCandidate) -> PassageOut:
        return PassageOut(
            passage_id=f"passage_{candidate.block_id}",
            source_id=candidate.source_id,
            source_version_id=candidate.source_version_id,
            source_name=candidate.source_name,
            page=candidate.page,
            section_path=candidate.section_path,
            block_id=candidate.block_id,
            offsets={"start": 0, "end": len(candidate.text)},
            text=candidate.text[:3000],
            score=round(score, 4),
        )

    @staticmethod
    def _version(backend_id: str) -> str:
        return "hybrid.pgvector.v2" if backend_id == "pgvector" else "hybrid.v2"
