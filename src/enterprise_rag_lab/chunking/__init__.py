"""Versioned structure-aware chunking API."""

from enterprise_rag_lab.chunking.chunker import (
    CHUNKER_VERSION,
    DEFAULT_MAX_CHARACTERS,
    DEFAULT_TARGET_CHARACTERS,
    MIN_TRAILING_CHUNK_CHARACTERS,
    chunk_blocks,
)
from enterprise_rag_lab.chunking.service import ChunkingService

__all__ = [
    "CHUNKER_VERSION",
    "DEFAULT_MAX_CHARACTERS",
    "DEFAULT_TARGET_CHARACTERS",
    "MIN_TRAILING_CHUNK_CHARACTERS",
    "ChunkingService",
    "chunk_blocks",
]