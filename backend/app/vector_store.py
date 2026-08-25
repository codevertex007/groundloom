"""Derived vector-index storage boundaries.

SQLite keeps the rebuildable embedding JSON used by the local adapter. Postgres
deployments additionally persist vectors in the pgvector table created by
migration 015 and can execute bounded semantic candidate search in the
database. This module never owns source authorization or citation lineage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import Settings
from .errors import GroundloomError


class VectorIndexStore(Protocol):
    @property
    def backend_id(self) -> str: ...

    def upsert(
        self,
        db: Session,
        *,
        workspace_id: str,
        source_version_id: str,
        source_chunk_id: str,
        vector: list[float],
    ) -> None: ...

    def delete_for_version(self, db: Session, *, workspace_id: str, source_version_id: str) -> None: ...

    def search(
        self,
        db: Session,
        *,
        workspace_id: str,
        source_version_ids: list[str],
        vector: list[float],
        limit: int,
    ) -> dict[str, float]: ...


@dataclass(frozen=True)
class LocalVectorIndexStore:
    """No-op store for SQLite; JSON embeddings remain the local derived index."""

    backend_id: str = "local-json"

    def upsert(
        self,
        db: Session,
        *,
        workspace_id: str,
        source_version_id: str,
        source_chunk_id: str,
        vector: list[float],
    ) -> None:
        return None

    def delete_for_version(self, db: Session, *, workspace_id: str, source_version_id: str) -> None:
        return None

    def search(
        self,
        db: Session,
        *,
        workspace_id: str,
        source_version_ids: list[str],
        vector: list[float],
        limit: int,
    ) -> dict[str, float]:
        return {}


def _vector_literal(vector: list[float]) -> str:
    if not vector or any(not math.isfinite(value) for value in vector):
        raise GroundloomError(
            "PROVIDER_INVALID_RESPONSE",
            "The embedding vector is empty or non-finite.",
            502,
        )
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


@dataclass(frozen=True)
class PgVectorIndexStore:
    backend_id: str = "pgvector"

    @staticmethod
    def _dependency_error(exc: Exception) -> GroundloomError:
        return GroundloomError(
            "DEPENDENCY_UNAVAILABLE",
            "The vector index is temporarily unavailable.",
            503,
            retryable=True,
        )

    def upsert(
        self,
        db: Session,
        *,
        workspace_id: str,
        source_version_id: str,
        source_chunk_id: str,
        vector: list[float],
    ) -> None:
        try:
            db.execute(
                text(
                    """
                    INSERT INTO source_chunk_embeddings
                        (source_chunk_id, workspace_id, source_version_id, dimensions,
                         embedding, created_at, updated_at)
                    VALUES
                        (:source_chunk_id, :workspace_id, :source_version_id, :dimensions,
                         CAST(:embedding AS vector), NOW(), NOW())
                    ON CONFLICT (source_chunk_id) DO UPDATE SET
                        workspace_id = EXCLUDED.workspace_id,
                        source_version_id = EXCLUDED.source_version_id,
                        dimensions = EXCLUDED.dimensions,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """
                ),
                {
                    "source_chunk_id": source_chunk_id,
                    "workspace_id": workspace_id,
                    "source_version_id": source_version_id,
                    "dimensions": len(vector),
                    "embedding": _vector_literal(vector),
                },
            )
        except SQLAlchemyError as exc:
            raise self._dependency_error(exc) from exc

    def delete_for_version(self, db: Session, *, workspace_id: str, source_version_id: str) -> None:
        try:
            db.execute(
                text(
                    "DELETE FROM source_chunk_embeddings "
                    "WHERE workspace_id = :workspace_id AND source_version_id = :source_version_id"
                ),
                {"workspace_id": workspace_id, "source_version_id": source_version_id},
            )
        except SQLAlchemyError as exc:
            raise self._dependency_error(exc) from exc

    def search(
        self,
        db: Session,
        *,
        workspace_id: str,
        source_version_ids: list[str],
        vector: list[float],
        limit: int,
    ) -> dict[str, float]:
        if not source_version_ids:
            return {}
        bounded_limit = max(1, min(limit, 100))
        statement = text(
            """
            SELECT sc.source_block_id,
                   1 - (sce.embedding <=> CAST(:embedding AS vector)) AS semantic_score
            FROM source_chunk_embeddings AS sce
            JOIN source_chunks AS sc ON sc.id = sce.source_chunk_id
            WHERE sce.workspace_id = :workspace_id
              AND sce.source_version_id IN :source_version_ids
              AND sce.dimensions = :dimensions
            ORDER BY sce.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ).bindparams(bindparam("source_version_ids", expanding=True))
        try:
            rows = db.execute(
                statement,
                {
                    "workspace_id": workspace_id,
                    "source_version_ids": source_version_ids,
                    "dimensions": len(vector),
                    "embedding": _vector_literal(vector),
                    "limit": bounded_limit,
                },
            )
        except SQLAlchemyError as exc:
            raise self._dependency_error(exc) from exc
        scores: dict[str, float] = {}
        for row in rows:
            block_id = str(row[0])
            score = max(0.0, min(1.0, float(row[1])))
            scores[block_id] = max(scores.get(block_id, 0.0), score)
        return scores


def build_vector_index_store(db: Session, settings: Settings | None = None) -> VectorIndexStore:
    settings = settings or Settings()
    backend = settings.retrieval_index_backend
    dialect = db.get_bind().dialect.name
    if backend == "auto":
        backend = "pgvector" if dialect == "postgresql" else "local"
    if backend == "local":
        return LocalVectorIndexStore()
    if backend == "pgvector" and dialect == "postgresql":
        return PgVectorIndexStore()
    raise GroundloomError(
        "PROVIDER_MISCONFIGURED",
        "The configured vector index backend requires PostgreSQL with pgvector.",
        503,
    )
