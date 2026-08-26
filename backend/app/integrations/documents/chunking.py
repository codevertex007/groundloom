"""Framework-backed, deterministic text splitting for derived retrieval chunks."""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass(frozen=True)
class IndexedTextChunk:
    """One bounded chunk and its offset in the immutable normalized block."""

    text: str
    start_index: int


def split_text_for_indexing(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[IndexedTextChunk, ...]:
    """Split text without owning source lineage or persistence.

    LangChain's recursive splitter preserves paragraphs/sentences where it can,
    while still enforcing a hard character bound for unusually large blocks.
    The returned offset remains relative to the normalized source block.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
    if not text.strip():
        return ()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    documents = splitter.create_documents([text])
    return tuple(
        IndexedTextChunk(
            text=document.page_content,
            start_index=max(0, int(document.metadata.get("start_index", 0))),
        )
        for document in documents
        if document.page_content
    )
