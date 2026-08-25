"""Authorized SQLAlchemy implementation of the AI retrieval repository."""

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

    def load(self, query_vector: list[float], candidate_limit: int) -> RetrievalSnapshot:
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

        rows = (
            self.db.query(SourceBlock, Source)
            .join(SourceVersion, SourceVersion.id == SourceBlock.source_version_id)
            .join(Source, Source.id == SourceVersion.source_id)
            .filter(
                SourceBlock.workspace_id == self.ctx.workspace_id,
                SourceBlock.source_version_id.in_(allowed),
            )
            .all()
        )
        vectors = {
            chunk.source_block_id: chunk.embedding_json
            for chunk in self.db.query(SourceChunk)
            .filter(
                SourceChunk.workspace_id == self.ctx.workspace_id,
                SourceChunk.source_version_id.in_(allowed),
            )
            .all()
        }
        vector_store = build_vector_index_store(self.db, self.settings)
        semantic_scores = vector_store.search(
            self.db,
            workspace_id=self.ctx.workspace_id,
            source_version_ids=sorted(allowed),
            vector=query_vector,
            limit=candidate_limit,
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
                embedding=vectors.get(block.id),
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
