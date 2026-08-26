"""Authorized SQLAlchemy implementation of the AI retrieval repository."""

import re

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ...ai.retrieval.contracts import RetrievalCandidate, RetrievalSnapshot
from ...ai.retrieval.providers.embeddings import build_embedding_provider
from ...ai.retrieval.providers.reranking import build_reranker
from ...ai.retrieval.service import RetrievalService
from ...config import Settings
from ...context import RuntimeContext
from ...errors import GroundloomError
from ...models import Project, ProjectConfigVersion, Source, SourceBlock, SourceChunk, SourceVersion
from ...schemas import EvidenceBundle
from ...vector_store import build_vector_index_store


class SqlAlchemyRetrievalRepository:
    def __init__(self, db: Session, ctx: RuntimeContext, project_id: str, settings: Settings):
        self.db = db
        self.ctx = ctx
        self.project_id = project_id
        self.settings = settings

    def load(
        self,
        query: str,
        query_vector: list[float],
        candidate_limit: int,
    ) -> RetrievalSnapshot:
        project = (
            self.db.query(Project)
            .filter_by(id=self.project_id, workspace_id=self.ctx.workspace_id)
            .first()
        )
        if project is None:
            raise GroundloomError("RESOURCE_NOT_FOUND", "The project was not found.", 404)
        config = self.db.get(ProjectConfigVersion, project.current_config_version_id)
        allowed = set(config.source_version_ids if config else [])
        if not allowed:
            return RetrievalSnapshot(
                has_source_scope=False,
                candidates=(),
                semantic_scores={},
                backend_id="local",
            )

        vector_store = build_vector_index_store(self.db, self.settings)
        semantic_scores = vector_store.search(
            self.db,
            workspace_id=self.ctx.workspace_id,
            source_version_ids=sorted(allowed),
            vector=query_vector,
            limit=candidate_limit,
        )
        base_query = (
            self.db.query(SourceBlock, Source)
            .join(SourceVersion, SourceVersion.id == SourceBlock.source_version_id)
            .join(Source, Source.id == SourceVersion.source_id)
            .filter(
                SourceBlock.workspace_id == self.ctx.workspace_id,
                SourceBlock.source_version_id.in_(allowed),
            )
        )
        if vector_store.backend_id == "pgvector":
            candidate_ids = set(semantic_scores)
            terms = list(dict.fromkeys(re.findall(r"[a-z0-9]{3,}", query.lower())))[:8]
            if terms:
                lexical_ids = (
                    self.db.query(SourceBlock.id)
                    .filter(
                        SourceBlock.workspace_id == self.ctx.workspace_id,
                        SourceBlock.source_version_id.in_(allowed),
                        or_(*(func.lower(SourceBlock.text).contains(term) for term in terms)),
                    )
                    .order_by(SourceBlock.source_version_id, SourceBlock.block_no, SourceBlock.id)
                    .limit(candidate_limit)
                    .all()
                )
                candidate_ids.update(str(row[0]) for row in lexical_ids)
            seed_rows = (
                [
                    (block, source)
                    for block, source in base_query.filter(
                        SourceBlock.id.in_(candidate_ids)
                    ).all()
                ]
                if candidate_ids
                else []
            )
            neighbor_filters = [
                and_(
                    SourceBlock.source_version_id == block.source_version_id,
                    SourceBlock.block_no.in_([block.block_no - 1, block.block_no + 1]),
                )
                for block, _source in seed_rows
            ]
            neighbor_rows = (
                [
                    (block, source)
                    for block, source in base_query.filter(or_(*neighbor_filters)).all()
                ]
                if neighbor_filters
                else []
            )
            by_id = {block.id: (block, source) for block, source in [*seed_rows, *neighbor_rows]}
            rows = sorted(
                by_id.values(),
                key=lambda item: (item[0].source_version_id, item[0].block_no, item[0].id),
            )
        else:
            # The SQLite adapter is deliberately local-only and has no ANN
            # index; scan the selected derived corpus to retain deterministic
            # developer behavior. Production is required to use pgvector.
            rows = [
                (block, source)
                for block, source in base_query.order_by(
                    SourceBlock.source_version_id,
                    SourceBlock.block_no,
                    SourceBlock.id,
                ).all()
            ]

        row_ids = [block.id for block, _source in rows]
        vector_rows = (
            self.db.query(SourceChunk)
            .filter(
                SourceChunk.workspace_id == self.ctx.workspace_id,
                SourceChunk.source_version_id.in_(allowed),
                SourceChunk.source_block_id.in_(row_ids),
            )
            .order_by(SourceChunk.source_block_id, SourceChunk.chunk_no)
            .all()
            if row_ids
            else []
        )
        vectors: dict[str, list[tuple[float, ...]]] = {}
        for chunk in vector_rows:
            if chunk.embedding_json:
                vectors.setdefault(chunk.source_block_id, []).append(
                    tuple(float(value) for value in chunk.embedding_json)
                )
        candidates = tuple(
            RetrievalCandidate(
                block_id=block.id,
                source_id=source.id,
                source_version_id=block.source_version_id,
                source_name=source.name,
                block_no=block.block_no,
                page=block.page_no,
                section_path=block.section_path,
                text=block.text,
                embeddings=tuple(vectors.get(block.id, [])),
            )
            for block, source in rows
        )
        return RetrievalSnapshot(
            has_source_scope=True,
            candidates=candidates,
            semantic_scores=semantic_scores,
            backend_id=vector_store.backend_id,
        )


def search_evidence(
    db: Session,
    ctx: RuntimeContext,
    project_id: str,
    query: str,
    limit: int = 8,
    settings: Settings | None = None,
) -> EvidenceBundle:
    resolved = settings or Settings()
    service = RetrievalService(
        SqlAlchemyRetrievalRepository(db, ctx, project_id, resolved),
        build_embedding_provider(resolved),
        build_reranker(resolved),
    )
    return service.search(query, limit)
