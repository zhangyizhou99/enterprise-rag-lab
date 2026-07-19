"""Versioned SQLite FTS5 trigram indexing and BM25 keyword retrieval."""

from __future__ import annotations

import hashlib

from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import KeywordIndexResult, KeywordSearchResult

KEYWORD_INDEXER_VERSION = "0.1.0"
KEYWORD_TOKENIZER = "trigram"
KEYWORD_RETRIEVER_VERSION = "0.2.0"
KEYWORD_RETRIEVER_ID = (
    f"bm25_fts5_{KEYWORD_TOKENIZER}_or_v{KEYWORD_RETRIEVER_VERSION}"
)


def _stable_index_id(chunking_id: str) -> str:
    identity = f"{chunking_id}:{KEYWORD_INDEXER_VERSION}:{KEYWORD_TOKENIZER}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"keyword_{digest}"


def _fts_query(query: str) -> str:
    normalized = " ".join(query.split())
    if len(normalized) < 3:
        raise ValueError("Keyword queries must contain at least 3 characters")

    runs: list[str] = []
    current: list[str] = []
    current_is_ascii: bool | None = None
    for character in normalized:
        if not (character.isalnum() or character == "_"):
            if current:
                runs.append("".join(current))
                current = []
                current_is_ascii = None
            continue
        is_ascii = character.isascii()
        if current and is_ascii != current_is_ascii:
            runs.append("".join(current))
            current = []
        current.append(character)
        current_is_ascii = is_ascii
    if current:
        runs.append("".join(current))

    trigrams = dict.fromkeys(
        run[offset : offset + 3]
        for run in runs
        for offset in range(len(run) - 2)
    )
    if not trigrams:
        escaped = normalized.replace(chr(34), chr(34) * 2)
        return f'"{escaped}"'
    return " OR ".join(
        f'"{trigram.replace(chr(34), chr(34) * 2)}"' for trigram in trigrams
    )


class KeywordSearchService:
    def __init__(self, store: SQLiteIngestionStore) -> None:
        self.store = store

    def index_document(self, document_id: str) -> KeywordIndexResult | None:
        source = self.store.get_latest_chunks(document_id)
        if source is None:
            return None
        chunking_id, chunks = source
        result = KeywordIndexResult(
            index_id=_stable_index_id(chunking_id),
            chunking_id=chunking_id,
            document_id=document_id,
            indexer_version=KEYWORD_INDEXER_VERSION,
            tokenizer=KEYWORD_TOKENIZER,
            indexed_chunk_count=len(chunks),
        )
        self.store.save_keyword_index(result, chunks)
        return result

    def search(self, query: str, limit: int = 10) -> tuple[KeywordSearchResult, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("Search limit must be between 1 and 100")
        return self.store.search_keyword(_fts_query(query), limit)