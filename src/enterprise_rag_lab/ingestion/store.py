"""SQLite persistence for documents, parser output, and ingestion runs."""

from __future__ import annotations

import json
import sqlite3
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from enterprise_rag_lab.models import (
    CleanResult,
    CleanedBlock,
    Chunk,
    ChunkEmbedding,
    ChunkResult,
    Document,
    DocumentVersion,
    IngestionRun,
    IngestionStatus,
    EmbeddingResult,
    KeywordIndexResult,
    KeywordSearchResult,
    ParseResult,
    ParsedBlock,
    VectorIndexResult,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source_format TEXT NOT NULL,
    content_type TEXT NOT NULL,
    source_path TEXT NOT NULL UNIQUE,
    source_uri TEXT,
    content_hash TEXT NOT NULL,
    index_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_canonical_id
ON documents(canonical_id);

CREATE TABLE IF NOT EXISTS document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    content_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parsed_blocks (
    version_id TEXT NOT NULL REFERENCES document_versions(version_id),
    ordinal INTEGER NOT NULL,
    block_type TEXT NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    heading_path_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY(version_id, ordinal)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL,
    document_id TEXT,
    error_code TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS cleaning_versions (
    cleaning_id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES document_versions(version_id),
    cleaner_version TEXT NOT NULL,
    rule_set_version TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    source_block_count INTEGER NOT NULL,
    cleaned_block_count INTEGER NOT NULL,
    removed_block_count INTEGER NOT NULL,
    modified_block_count INTEGER NOT NULL,
    source_character_count INTEGER NOT NULL,
    cleaned_character_count INTEGER NOT NULL,
    rule_hit_counts_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_version_id, cleaner_version, rule_set_version)
);

CREATE TABLE IF NOT EXISTS cleaned_blocks (
    cleaning_id TEXT NOT NULL REFERENCES cleaning_versions(cleaning_id),
    ordinal INTEGER NOT NULL,
    source_ordinal INTEGER NOT NULL,
    block_type TEXT NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    heading_path_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY(cleaning_id, ordinal)
);

CREATE TABLE IF NOT EXISTS cleaning_rule_hits (
    cleaning_id TEXT NOT NULL REFERENCES cleaning_versions(cleaning_id),
    hit_ordinal INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    source_ordinal INTEGER NOT NULL,
    action TEXT NOT NULL,
    before_text TEXT NOT NULL,
    after_text TEXT,
    PRIMARY KEY(cleaning_id, hit_ordinal)
);

CREATE TABLE IF NOT EXISTS chunking_versions (
    chunking_id TEXT PRIMARY KEY,
    cleaning_id TEXT NOT NULL REFERENCES cleaning_versions(cleaning_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chunker_version TEXT NOT NULL,
    target_characters INTEGER NOT NULL,
    max_characters INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cleaning_id, chunker_version, target_characters, max_characters)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    chunking_id TEXT NOT NULL REFERENCES chunking_versions(chunking_id),
    cleaning_id TEXT NOT NULL REFERENCES cleaning_versions(cleaning_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    ordinal INTEGER NOT NULL,
    parent_id TEXT NOT NULL,
    text TEXT NOT NULL,
    heading_path_json TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    source_ordinals_json TEXT NOT NULL,
    previous_chunk_id TEXT,
    next_chunk_id TEXT,
    metadata_json TEXT NOT NULL,
    UNIQUE(chunking_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id
ON chunks(document_id);

CREATE TABLE IF NOT EXISTS keyword_index_versions (
    index_id TEXT PRIMARY KEY,
    chunking_id TEXT NOT NULL REFERENCES chunking_versions(chunking_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    indexer_version TEXT NOT NULL,
    tokenizer TEXT NOT NULL,
    indexed_chunk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chunking_id, indexer_version, tokenizer)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    index_id UNINDEXED,
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    title,
    heading_path,
    text,
    tokenize='trigram'
);

CREATE TABLE IF NOT EXISTS embedding_versions (
    embedding_id TEXT PRIMARY KEY,
    chunking_id TEXT NOT NULL REFERENCES chunking_versions(chunking_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    embedder_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK(dimension > 0),
    normalized INTEGER NOT NULL CHECK(normalized IN (0, 1)),
    passage_prefix TEXT NOT NULL,
    max_sequence_length INTEGER NOT NULL CHECK(max_sequence_length > 0),
    embedded_chunk_count INTEGER NOT NULL,
    truncated_chunk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(
        chunking_id, embedder_version, model_name, model_revision,
        normalized, passage_prefix
    )
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    embedding_id TEXT NOT NULL REFERENCES embedding_versions(embedding_id),
    chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id),
    ordinal INTEGER NOT NULL,
    vector BLOB NOT NULL,
    token_count INTEGER NOT NULL CHECK(token_count > 0),
    truncated INTEGER NOT NULL CHECK(truncated IN (0, 1)),
    PRIMARY KEY(embedding_id, chunk_id),
    UNIQUE(embedding_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_embedding_versions_document_id
ON embedding_versions(document_id);

CREATE TABLE IF NOT EXISTS vector_index_versions (
    vector_index_id TEXT PRIMARY KEY,
    collection_name TEXT NOT NULL UNIQUE,
    indexer_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK(dimension > 0),
    distance TEXT NOT NULL,
    normalized INTEGER NOT NULL CHECK(normalized IN (0, 1)),
    passage_prefix TEXT NOT NULL,
    query_prefix TEXT NOT NULL,
    max_sequence_length INTEGER NOT NULL CHECK(max_sequence_length > 0),
    indexed_document_count INTEGER NOT NULL,
    indexed_chunk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vector_index_members (
    vector_index_id TEXT NOT NULL REFERENCES vector_index_versions(vector_index_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chunking_id TEXT NOT NULL REFERENCES chunking_versions(chunking_id),
    embedding_id TEXT NOT NULL REFERENCES embedding_versions(embedding_id),
    indexed_chunk_count INTEGER NOT NULL,
    PRIMARY KEY(vector_index_id, document_id),
    UNIQUE(vector_index_id, embedding_id)
);
"""


class SQLiteIngestionStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def start_run(self, run: IngestionRun) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_runs(run_id, source_path, status) VALUES (?, ?, ?)",
                (run.run_id, run.source_path, run.status.value),
            )

    def save_success(
        self,
        run: IngestionRun,
        document: Document,
        version: DocumentVersion,
        result: ParseResult,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents(
                    document_id, canonical_id, title, source_format, content_type,
                    source_path, source_uri, content_hash, index_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    canonical_id = excluded.canonical_id,
                    title = excluded.title,
                    source_format = excluded.source_format,
                    content_type = excluded.content_type,
                    source_uri = excluded.source_uri,
                    content_hash = excluded.content_hash,
                    index_status = excluded.index_status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    document.document_id,
                    document.canonical_id,
                    document.title,
                    document.source_format.value,
                    document.content_type,
                    document.source_path,
                    document.source_uri,
                    document.content_hash,
                    document.index_status,
                ),
            )
            connection.execute(
                """
                INSERT INTO document_versions(
                    version_id, document_id, content_hash, parser_version,
                    extracted_text, warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_id) DO UPDATE SET
                    extracted_text = excluded.extracted_text,
                    warnings_json = excluded.warnings_json
                """,
                (
                    version.version_id,
                    version.document_id,
                    version.content_hash,
                    version.parser_version,
                    version.extracted_text,
                    json.dumps(version.warnings, ensure_ascii=False),
                ),
            )
            connection.execute(
                "DELETE FROM parsed_blocks WHERE version_id = ?",
                (version.version_id,),
            )
            connection.executemany(
                """
                INSERT INTO parsed_blocks(
                    version_id, ordinal, block_type, text, page_number,
                    heading_path_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        version.version_id,
                        block.ordinal,
                        block.block_type,
                        block.text,
                        block.page_number,
                        json.dumps(block.heading_path, ensure_ascii=False),
                        json.dumps(block.metadata, ensure_ascii=False),
                    )
                    for block in result.blocks
                ],
            )
            connection.execute(
                """
                UPDATE ingestion_runs
                SET status = ?, document_id = ?, duration_ms = ?, finished_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (
                    IngestionStatus.SUCCEEDED.value,
                    document.document_id,
                    run.duration_ms,
                    run.run_id,
                ),
            )

    def save_failure(self, run: IngestionRun) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET status = ?, error_code = ?, error_message = ?,
                    duration_ms = ?, finished_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (
                    IngestionStatus.FAILED.value,
                    run.error_code,
                    run.error_message,
                    run.duration_ms,
                    run.run_id,
                ),
            )

    def get_run(self, run_id: str) -> IngestionRun | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ingestion_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return IngestionRun(
            run_id=row["run_id"],
            source_path=row["source_path"],
            status=IngestionStatus(row["status"]),
            document_id=row["document_id"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            duration_ms=row["duration_ms"],
        )

    def get_document(self, document_id: str) -> Document | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        from enterprise_rag_lab.models import SourceFormat

        return Document(
            document_id=row["document_id"],
            canonical_id=row["canonical_id"],
            title=row["title"],
            source_format=SourceFormat(row["source_format"]),
            content_type=row["content_type"],
            source_path=row["source_path"],
            source_uri=row["source_uri"],
            content_hash=row["content_hash"],
            index_status=row["index_status"],
        )

    def list_documents(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, canonical_id, title, source_format, content_type,
                       source_path, source_uri, content_hash, index_status,
                       created_at, updated_at
                FROM documents
                ORDER BY created_at, document_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def inspect_document(self, document_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            document = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if document is None:
                return None
            versions = connection.execute(
                """
                SELECT version_id, content_hash, parser_version, warnings_json,
                       created_at, LENGTH(extracted_text) AS extracted_text_length,
                       (SELECT COUNT(*) FROM parsed_blocks blocks
                        WHERE blocks.version_id = document_versions.version_id) AS block_count
                FROM document_versions
                WHERE document_id = ?
                ORDER BY created_at, version_id
                """,
                (document_id,),
            ).fetchall()
        result = dict(document)
        result["versions"] = [
            {
                **dict(version),
                "warnings": json.loads(version["warnings_json"]),
            }
            for version in versions
        ]
        for version in result["versions"]:
            version.pop("warnings_json")
        return result

    def list_blocks(
        self,
        document_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT blocks.version_id, blocks.ordinal, blocks.block_type,
                       blocks.text, blocks.page_number, blocks.heading_path_json,
                       blocks.metadata_json
                FROM parsed_blocks blocks
                JOIN document_versions versions ON versions.version_id = blocks.version_id
                WHERE versions.document_id = ?
                ORDER BY versions.created_at DESC, blocks.ordinal
                LIMIT ? OFFSET ?
                """,
                (document_id, limit, offset),
            ).fetchall()
        return [
            {
                **{
                    key: value
                    for key, value in dict(row).items()
                    if key not in {"heading_path_json", "metadata_json"}
                },
                "heading_path": json.loads(row["heading_path_json"]),
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def get_latest_parsed_version(
        self,
        document_id: str,
    ) -> tuple[str, tuple[ParsedBlock, ...]] | None:
        with self._connect() as connection:
            version = connection.execute(
                """
                SELECT version_id
                FROM document_versions
                WHERE document_id = ?
                ORDER BY created_at DESC, version_id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            if version is None:
                return None
            rows = connection.execute(
                """
                SELECT ordinal, block_type, text, page_number,
                       heading_path_json, metadata_json
                FROM parsed_blocks
                WHERE version_id = ?
                ORDER BY ordinal
                """,
                (version["version_id"],),
            ).fetchall()
        blocks = tuple(
            ParsedBlock(
                ordinal=row["ordinal"],
                text=row["text"],
                block_type=row["block_type"],
                page_number=row["page_number"],
                heading_path=tuple(json.loads(row["heading_path_json"])),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        )
        return version["version_id"], blocks

    def save_cleaning(self, result: CleanResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cleaning_versions(
                    cleaning_id, source_version_id, cleaner_version,
                    rule_set_version, cleaned_text, source_block_count,
                    cleaned_block_count, removed_block_count,
                    modified_block_count, source_character_count,
                    cleaned_character_count, rule_hit_counts_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cleaning_id) DO UPDATE SET
                    cleaned_text = excluded.cleaned_text,
                    source_block_count = excluded.source_block_count,
                    cleaned_block_count = excluded.cleaned_block_count,
                    removed_block_count = excluded.removed_block_count,
                    modified_block_count = excluded.modified_block_count,
                    source_character_count = excluded.source_character_count,
                    cleaned_character_count = excluded.cleaned_character_count,
                    rule_hit_counts_json = excluded.rule_hit_counts_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    result.cleaning_id,
                    result.source_version_id,
                    result.cleaner_version,
                    result.rule_set_version,
                    result.text,
                    result.stats.source_block_count,
                    result.stats.cleaned_block_count,
                    result.stats.removed_block_count,
                    result.stats.modified_block_count,
                    result.stats.source_character_count,
                    result.stats.cleaned_character_count,
                    json.dumps(result.stats.rule_hit_counts, ensure_ascii=False),
                ),
            )
            connection.execute(
                "DELETE FROM cleaned_blocks WHERE cleaning_id = ?",
                (result.cleaning_id,),
            )
            connection.execute(
                "DELETE FROM cleaning_rule_hits WHERE cleaning_id = ?",
                (result.cleaning_id,),
            )
            connection.executemany(
                """
                INSERT INTO cleaned_blocks(
                    cleaning_id, ordinal, source_ordinal, block_type, text,
                    page_number, heading_path_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.cleaning_id,
                        block.ordinal,
                        block.source_ordinal,
                        block.block_type,
                        block.text,
                        block.page_number,
                        json.dumps(block.heading_path, ensure_ascii=False),
                        json.dumps(block.metadata, ensure_ascii=False),
                    )
                    for block in result.blocks
                ],
            )
            connection.executemany(
                """
                INSERT INTO cleaning_rule_hits(
                    cleaning_id, hit_ordinal, rule_id, source_ordinal,
                    action, before_text, after_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.cleaning_id,
                        hit_ordinal,
                        hit.rule_id,
                        hit.source_ordinal,
                        hit.action,
                        hit.before_text,
                        hit.after_text,
                    )
                    for hit_ordinal, hit in enumerate(result.hits)
                ],
            )

    def inspect_cleaning(self, document_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            cleaning = connection.execute(
                """
                  SELECT cleaning.*, documents.document_id, documents.title,
                      documents.source_format
                FROM cleaning_versions cleaning
                JOIN document_versions versions
                  ON versions.version_id = cleaning.source_version_id
                JOIN documents ON documents.document_id = versions.document_id
                WHERE documents.document_id = ?
                ORDER BY cleaning.created_at DESC, cleaning.cleaning_id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            if cleaning is None:
                return None
            hits = connection.execute(
                """
                SELECT hit_ordinal, rule_id, source_ordinal, action,
                       before_text, after_text
                FROM cleaning_rule_hits
                WHERE cleaning_id = ?
                ORDER BY hit_ordinal
                """,
                (cleaning["cleaning_id"],),
            ).fetchall()
        result = {
            key: value
            for key, value in dict(cleaning).items()
            if key not in {"cleaned_text", "rule_hit_counts_json"}
        }
        result["character_delta"] = (
            cleaning["cleaned_character_count"] - cleaning["source_character_count"]
        )
        result["rule_hit_counts"] = json.loads(cleaning["rule_hit_counts_json"])
        result["rule_hits"] = [dict(hit) for hit in hits]
        return result

    def get_parsed_blocks(self, version_id: str) -> tuple[ParsedBlock, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT ordinal, block_type, text, page_number,
                       heading_path_json, metadata_json
                FROM parsed_blocks
                WHERE version_id = ?
                ORDER BY ordinal
                """,
                (version_id,),
            ).fetchall()
        return tuple(
            ParsedBlock(
                ordinal=row["ordinal"],
                text=row["text"],
                block_type=row["block_type"],
                page_number=row["page_number"],
                heading_path=tuple(json.loads(row["heading_path_json"])),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        )

    def get_cleaned_blocks(self, cleaning_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT ordinal, source_ordinal, block_type, text, page_number,
                       heading_path_json, metadata_json
                FROM cleaned_blocks
                WHERE cleaning_id = ?
                ORDER BY ordinal
                """,
                (cleaning_id,),
            ).fetchall()
        return [
            {
                **{
                    key: value
                    for key, value in dict(row).items()
                    if key not in {"heading_path_json", "metadata_json"}
                },
                "heading_path": json.loads(row["heading_path_json"]),
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def get_latest_cleaning(
        self,
        document_id: str,
    ) -> tuple[str, tuple[CleanedBlock, ...]] | None:
        with self._connect() as connection:
            cleaning = connection.execute(
                """
                SELECT cleaning.cleaning_id
                FROM cleaning_versions cleaning
                JOIN document_versions versions
                  ON versions.version_id = cleaning.source_version_id
                WHERE versions.document_id = ?
                ORDER BY cleaning.created_at DESC, cleaning.cleaning_id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            if cleaning is None:
                return None
            rows = connection.execute(
                """
                SELECT ordinal, source_ordinal, block_type, text, page_number,
                       heading_path_json, metadata_json
                FROM cleaned_blocks
                WHERE cleaning_id = ?
                ORDER BY ordinal
                """,
                (cleaning["cleaning_id"],),
            ).fetchall()
        blocks = tuple(
            CleanedBlock(
                ordinal=row["ordinal"],
                source_ordinal=row["source_ordinal"],
                text=row["text"],
                block_type=row["block_type"],
                page_number=row["page_number"],
                heading_path=tuple(json.loads(row["heading_path_json"])),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        )
        return cleaning["cleaning_id"], blocks

    def save_chunking(self, result: ChunkResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chunking_versions(
                    chunking_id, cleaning_id, document_id, chunker_version,
                    target_characters, max_characters, chunk_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunking_id) DO UPDATE SET
                    chunk_count = excluded.chunk_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    result.chunking_id,
                    result.cleaning_id,
                    result.document_id,
                    result.chunker_version,
                    result.target_characters,
                    result.max_characters,
                    len(result.chunks),
                ),
            )
            connection.execute(
                "DELETE FROM chunks WHERE chunking_id = ?",
                (result.chunking_id,),
            )
            connection.executemany(
                """
                INSERT INTO chunks(
                    chunk_id, chunking_id, cleaning_id, document_id, ordinal,
                    parent_id, text, heading_path_json, page_start, page_end,
                    source_ordinals_json, previous_chunk_id, next_chunk_id,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.chunking_id,
                        chunk.cleaning_id,
                        chunk.document_id,
                        chunk.ordinal,
                        chunk.parent_id,
                        chunk.text,
                        json.dumps(chunk.heading_path, ensure_ascii=False),
                        chunk.page_start,
                        chunk.page_end,
                        json.dumps(chunk.source_ordinals, ensure_ascii=False),
                        chunk.previous_chunk_id,
                        chunk.next_chunk_id,
                        json.dumps(chunk.metadata, ensure_ascii=False),
                    )
                    for chunk in result.chunks
                ],
            )

    def inspect_chunking(self, document_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT chunking.*, documents.title,
                       MIN(LENGTH(chunks.text)) AS min_chunk_characters,
                       CAST(AVG(LENGTH(chunks.text)) AS INTEGER) AS avg_chunk_characters,
                       MAX(LENGTH(chunks.text)) AS max_chunk_characters
                FROM chunking_versions chunking
                JOIN documents ON documents.document_id = chunking.document_id
                LEFT JOIN chunks ON chunks.chunking_id = chunking.chunking_id
                WHERE chunking.document_id = ?
                GROUP BY chunking.chunking_id
                ORDER BY chunking.created_at DESC, chunking.chunking_id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_chunks(
        self,
        document_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunks.*
                FROM chunks
                WHERE chunks.document_id = ?
                  AND chunks.chunking_id = (
                      SELECT chunking_id
                      FROM chunking_versions
                      WHERE document_id = ?
                      ORDER BY created_at DESC, chunking_id DESC
                      LIMIT 1
                  )
                ORDER BY chunks.ordinal
                LIMIT ? OFFSET ?
                """,
                (document_id, document_id, limit, offset),
            ).fetchall()
        return [
            {
                **{
                    key: value
                    for key, value in dict(row).items()
                    if key not in {
                        "heading_path_json",
                        "source_ordinals_json",
                        "metadata_json",
                    }
                },
                "heading_path": json.loads(row["heading_path_json"]),
                "source_ordinals": json.loads(row["source_ordinals_json"]),
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def get_latest_chunks(
        self,
        document_id: str,
    ) -> tuple[str, tuple[Chunk, ...]] | None:
        with self._connect() as connection:
            chunking = connection.execute(
                """
                SELECT rowid, chunking_id
                FROM chunking_versions
                WHERE document_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            if chunking is None:
                return None
            rows = connection.execute(
                """
                SELECT *
                FROM chunks
                WHERE chunking_id = ?
                ORDER BY ordinal
                """,
                (chunking["chunking_id"],),
            ).fetchall()
        chunks = tuple(
            Chunk(
                chunk_id=row["chunk_id"],
                chunking_id=row["chunking_id"],
                cleaning_id=row["cleaning_id"],
                document_id=row["document_id"],
                ordinal=row["ordinal"],
                parent_id=row["parent_id"],
                text=row["text"],
                heading_path=tuple(json.loads(row["heading_path_json"])),
                page_start=row["page_start"],
                page_end=row["page_end"],
                source_ordinals=tuple(json.loads(row["source_ordinals_json"])),
                previous_chunk_id=row["previous_chunk_id"],
                next_chunk_id=row["next_chunk_id"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        )
        return chunking["chunking_id"], chunks

    def save_keyword_index(
        self,
        result: KeywordIndexResult,
        chunks: tuple[Chunk, ...],
    ) -> None:
        with self._connect() as connection:
            document = connection.execute(
                "SELECT title FROM documents WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            if document is None:
                raise ValueError(f"Unknown document: {result.document_id}")
            connection.execute(
                """
                INSERT INTO keyword_index_versions(
                    index_id, chunking_id, document_id, indexer_version,
                    tokenizer, indexed_chunk_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_id) DO UPDATE SET
                    indexed_chunk_count = excluded.indexed_chunk_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    result.index_id,
                    result.chunking_id,
                    result.document_id,
                    result.indexer_version,
                    result.tokenizer,
                    result.indexed_chunk_count,
                ),
            )
            connection.execute(
                "DELETE FROM chunk_fts WHERE index_id = ?",
                (result.index_id,),
            )
            connection.executemany(
                """
                INSERT INTO chunk_fts(
                    index_id, chunk_id, document_id, title, heading_path, text
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.index_id,
                        chunk.chunk_id,
                        chunk.document_id,
                        document["title"],
                        " > ".join(chunk.heading_path),
                        chunk.text,
                    )
                    for chunk in chunks
                ],
            )
            connection.execute(
                """
                UPDATE documents
                SET index_status = 'keyword_indexed', updated_at = CURRENT_TIMESTAMP
                WHERE document_id = ?
                """,
                (result.document_id,),
            )

    def inspect_keyword_index(self, document_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT indexes.*, documents.title
                FROM keyword_index_versions indexes
                JOIN documents ON documents.document_id = indexes.document_id
                WHERE indexes.document_id = ?
                ORDER BY indexes.created_at DESC, indexes.rowid DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def save_embeddings(self, result: EmbeddingResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO embedding_versions(
                    embedding_id, chunking_id, document_id, embedder_version,
                    model_name, model_revision, dimension, normalized,
                    passage_prefix, max_sequence_length, embedded_chunk_count,
                    truncated_chunk_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(embedding_id) DO UPDATE SET
                    dimension = excluded.dimension,
                    max_sequence_length = excluded.max_sequence_length,
                    embedded_chunk_count = excluded.embedded_chunk_count,
                    truncated_chunk_count = excluded.truncated_chunk_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    result.embedding_id,
                    result.chunking_id,
                    result.document_id,
                    result.embedder_version,
                    result.model_name,
                    result.model_revision,
                    result.dimension,
                    result.normalized,
                    result.passage_prefix,
                    result.max_sequence_length,
                    len(result.embeddings),
                    sum(embedding.truncated for embedding in result.embeddings),
                ),
            )
            connection.execute(
                "DELETE FROM chunk_embeddings WHERE embedding_id = ?",
                (result.embedding_id,),
            )
            connection.executemany(
                """
                INSERT INTO chunk_embeddings(
                    embedding_id, chunk_id, ordinal, vector,
                    token_count, truncated
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.embedding_id,
                        embedding.chunk_id,
                        embedding.ordinal,
                        struct.pack(f"<{result.dimension}f", *embedding.vector),
                        embedding.token_count,
                        embedding.truncated,
                    )
                    for embedding in result.embeddings
                ],
            )

    def inspect_embedding(self, document_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT versions.*,
                       MIN(vectors.token_count) AS min_token_count,
                       CAST(AVG(vectors.token_count) AS INTEGER) AS avg_token_count,
                       MAX(vectors.token_count) AS max_token_count
                FROM embedding_versions versions
                LEFT JOIN chunk_embeddings vectors
                  ON vectors.embedding_id = versions.embedding_id
                WHERE versions.document_id = ?
                GROUP BY versions.embedding_id
                ORDER BY versions.created_at DESC, versions.rowid DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["normalized"] = bool(result["normalized"])
        return result

    def get_embeddings(self, embedding_id: str) -> tuple[ChunkEmbedding, ...]:
        with self._connect() as connection:
            version = connection.execute(
                "SELECT dimension FROM embedding_versions WHERE embedding_id = ?",
                (embedding_id,),
            ).fetchone()
            if version is None:
                return ()
            rows = connection.execute(
                """
                SELECT chunk_id, ordinal, vector, token_count, truncated
                FROM chunk_embeddings
                WHERE embedding_id = ?
                ORDER BY ordinal
                """,
                (embedding_id,),
            ).fetchall()
        dimension = version["dimension"]
        return tuple(
            ChunkEmbedding(
                chunk_id=row["chunk_id"],
                ordinal=row["ordinal"],
                vector=tuple(struct.unpack(f"<{dimension}f", row["vector"])),
                token_count=row["token_count"],
                truncated=bool(row["truncated"]),
            )
            for row in rows
        )

    def save_vector_index(self, result: VectorIndexResult) -> None:
        indexed_chunk_count = sum(
            member.indexed_chunk_count for member in result.members
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vector_index_versions(
                    vector_index_id, collection_name, indexer_version,
                    model_name, model_revision, dimension, distance,
                    normalized, passage_prefix, query_prefix,
                    max_sequence_length, indexed_document_count,
                    indexed_chunk_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vector_index_id) DO UPDATE SET
                    indexed_document_count = excluded.indexed_document_count,
                    indexed_chunk_count = excluded.indexed_chunk_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    result.vector_index_id,
                    result.collection_name,
                    result.indexer_version,
                    result.model_name,
                    result.model_revision,
                    result.dimension,
                    result.distance,
                    result.normalized,
                    result.passage_prefix,
                    result.query_prefix,
                    result.max_sequence_length,
                    len(result.members),
                    indexed_chunk_count,
                ),
            )
            connection.execute(
                "DELETE FROM vector_index_members WHERE vector_index_id = ?",
                (result.vector_index_id,),
            )
            connection.executemany(
                """
                INSERT INTO vector_index_members(
                    vector_index_id, document_id, chunking_id,
                    embedding_id, indexed_chunk_count
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.vector_index_id,
                        member.document_id,
                        member.chunking_id,
                        member.embedding_id,
                        member.indexed_chunk_count,
                    )
                    for member in result.members
                ],
            )

    def inspect_vector_index(self) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT versions.*,
                       COUNT(members.document_id) AS stored_member_count
                FROM vector_index_versions versions
                LEFT JOIN vector_index_members members
                  ON members.vector_index_id = versions.vector_index_id
                GROUP BY versions.vector_index_id
                ORDER BY versions.created_at DESC, versions.rowid DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["normalized"] = bool(result["normalized"])
        return result

    def search_keyword(
        self,
        fts_query: str,
        limit: int,
    ) -> tuple[KeywordSearchResult, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunks.chunk_id, chunks.document_id, documents.title,
                       chunks.text, chunks.heading_path_json, chunks.page_start,
                       chunks.page_end, documents.source_uri,
                       snippet(chunk_fts, 5, '[', ']', '...', 24) AS snippet,
                       bm25(chunk_fts, 0.0, 0.0, 0.0, 5.0, 3.0, 1.0) AS raw_score
                FROM chunk_fts
                JOIN keyword_index_versions indexes
                  ON indexes.index_id = chunk_fts.index_id
                JOIN chunks ON chunks.chunk_id = chunk_fts.chunk_id
                JOIN documents ON documents.document_id = chunks.document_id
                WHERE chunk_fts MATCH ?
                  AND indexes.rowid = (
                      SELECT latest.rowid
                      FROM keyword_index_versions latest
                      WHERE latest.document_id = indexes.document_id
                      ORDER BY latest.created_at DESC, latest.rowid DESC
                      LIMIT 1
                  )
                ORDER BY raw_score, chunks.document_id, chunks.ordinal
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return tuple(
            KeywordSearchResult(
                rank=rank,
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                title=row["title"],
                text=row["text"],
                snippet=row["snippet"],
                score=-float(row["raw_score"]),
                heading_path=tuple(json.loads(row["heading_path_json"])),
                page_start=row["page_start"],
                page_end=row["page_end"],
                source_uri=row["source_uri"],
            )
            for rank, row in enumerate(rows, start=1)
        )

    def list_cleaned_blocks(
        self,
        document_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT blocks.cleaning_id, blocks.ordinal, blocks.source_ordinal,
                       blocks.block_type, blocks.text, blocks.page_number,
                       blocks.heading_path_json, blocks.metadata_json
                FROM cleaned_blocks blocks
                JOIN cleaning_versions cleaning
                  ON cleaning.cleaning_id = blocks.cleaning_id
                JOIN document_versions versions
                  ON versions.version_id = cleaning.source_version_id
                WHERE versions.document_id = ?
                  AND cleaning.cleaning_id = (
                      SELECT latest.cleaning_id
                      FROM cleaning_versions latest
                      JOIN document_versions latest_version
                        ON latest_version.version_id = latest.source_version_id
                      WHERE latest_version.document_id = ?
                      ORDER BY latest.created_at DESC, latest.cleaning_id DESC
                      LIMIT 1
                  )
                ORDER BY blocks.ordinal
                LIMIT ? OFFSET ?
                """,
                (document_id, document_id, limit, offset),
            ).fetchall()
        return [
            {
                **{
                    key: value
                    for key, value in dict(row).items()
                    if key not in {"heading_path_json", "metadata_json"}
                },
                "heading_path": json.loads(row["heading_path_json"]),
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def count_blocks(self, version_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM parsed_blocks WHERE version_id = ?",
                (version_id,),
            ).fetchone()
        return int(row["count"])