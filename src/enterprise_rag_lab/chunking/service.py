"""Create and persist deterministic chunks from the latest cleaning version."""

from __future__ import annotations

from enterprise_rag_lab.chunking.chunker import (
    DEFAULT_MAX_CHARACTERS,
    DEFAULT_TARGET_CHARACTERS,
    chunk_blocks,
)
from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import ChunkResult


class ChunkingService:
    def __init__(self, store: SQLiteIngestionStore) -> None:
        self.store = store

    def chunk_document(
        self,
        document_id: str,
        target_characters: int = DEFAULT_TARGET_CHARACTERS,
        max_characters: int = DEFAULT_MAX_CHARACTERS,
    ) -> ChunkResult | None:
        source = self.store.get_latest_cleaning(document_id)
        if source is None:
            return None
        cleaning_id, blocks = source
        result = chunk_blocks(
            document_id=document_id,
            cleaning_id=cleaning_id,
            blocks=blocks,
            target_characters=target_characters,
            max_characters=max_characters,
        )
        self.store.save_chunking(result)
        return result