"""Replay versioned cleaning rules against persisted parser output."""

from __future__ import annotations

import hashlib

from enterprise_rag_lab.cleaning.cleaner import (
    CLEANER_VERSION,
    RULE_SET_VERSION,
    clean_blocks,
)
from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import CleanResult


def _cleaning_id(source_version_id: str) -> str:
    identity = f"{source_version_id}:{CLEANER_VERSION}:{RULE_SET_VERSION}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"cleaning_{digest}"


class CleaningService:
    def __init__(self, store: SQLiteIngestionStore) -> None:
        self.store = store

    def clean_document(self, document_id: str) -> CleanResult | None:
        source = self.store.get_latest_parsed_version(document_id)
        if source is None:
            return None
        source_version_id, parsed_blocks = source
        blocks, hits, stats = clean_blocks(parsed_blocks)
        result = CleanResult(
            cleaning_id=_cleaning_id(source_version_id),
            source_version_id=source_version_id,
            cleaner_version=CLEANER_VERSION,
            rule_set_version=RULE_SET_VERSION,
            text="\n\n".join(block.text for block in blocks),
            blocks=blocks,
            hits=hits,
            stats=stats,
        )
        self.store.save_cleaning(result)
        return result