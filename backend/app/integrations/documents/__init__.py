"""Document parsing and deterministic derived-text preparation adapters."""

from .chunking import IndexedTextChunk, split_text_for_indexing
from .parsers import parse_source

__all__ = ["IndexedTextChunk", "parse_source", "split_text_for_indexing"]
