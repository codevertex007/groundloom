"""Derived source-chunk indexing behind the authorized application boundary."""

import re
from collections.abc import Sequence

from sqlalchemy.orm import Session

from ...ai.retrieval.providers.embeddings import build_embedding_provider
from ...config import Settings
from ...errors import GroundloomError
from ...ids import new_id
from ...models import SourceBlock, SourceChunk
from ...vector_store import build_vector_index_store
from ..documents.chunking import IndexedTextChunk, split_text_for_indexing


def replace_source_version_index(
    db: Session,
    settings: Settings,
    blocks: Sequence[SourceBlock],
    *,
    clear_existing: bool,
) -> int:
    """Build the complete rebuildable chunk/vector projection for source blocks.

    Both initial ingestion and explicit rebuilds call this function so chunking,
    embedding batches, lexical terms, and vector persistence cannot diverge.
    """

    if not blocks:
        return 0
    workspace_id = blocks[0].workspace_id
    source_version_id = blocks[0].source_version_id
    if any(
        block.workspace_id != workspace_id or block.source_version_id != source_version_id
        for block in blocks
    ):
        raise ValueError("All indexed source blocks must share one trusted source scope")

    vector_store = build_vector_index_store(db, settings)
    if clear_existing:
        vector_store.delete_for_version(
            db,
            workspace_id=workspace_id,
            source_version_id=source_version_id,
        )
        db.query(SourceChunk).filter_by(
            workspace_id=workspace_id,
            source_version_id=source_version_id,
        ).delete(synchronize_session=False)

    pending: list[tuple[SourceBlock, int, IndexedTextChunk]] = []
    for block in blocks:
        chunks = split_text_for_indexing(
            block.text,
            chunk_size=settings.source_chunk_size,
            chunk_overlap=settings.source_chunk_overlap,
        )
        pending.extend((block, chunk_no, chunk) for chunk_no, chunk in enumerate(chunks))

    provider = build_embedding_provider(settings)
    created = 0
    batch_size = settings.embedding_batch_size
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        vectors = provider.embed([chunk.text for _block, _chunk_no, chunk in batch])
        if len(vectors) != len(batch):
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The embedding provider returned an incomplete batch.",
                502,
            )
        for (block, chunk_no, chunk), vector in zip(batch, vectors, strict=True):
            row = SourceChunk(
                id=new_id("chk"),
                workspace_id=workspace_id,
                source_version_id=source_version_id,
                source_block_id=block.id,
                chunk_no=chunk_no,
                text=chunk.text,
                token_terms=sorted(set(re.findall(r"[a-z0-9]{3,}", chunk.text.lower()))),
                embedding_json=vector,
            )
            db.add(row)
            db.flush()
            vector_store.upsert(
                db,
                workspace_id=workspace_id,
                source_version_id=source_version_id,
                source_chunk_id=row.id,
                vector=vector,
            )
            created += 1
    return created
