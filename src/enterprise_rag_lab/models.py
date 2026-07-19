"""Shared document contracts for parsing, ingestion, and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SourceFormat(StrEnum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """A source-addressable unit emitted by a parser before chunking."""

    ordinal: int
    text: str
    block_type: str = "paragraph"
    page_number: int | None = None
    heading_path: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseResult:
    source_path: Path
    source_format: SourceFormat
    title: str
    text: str
    blocks: tuple[ParsedBlock, ...]
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CleanedBlock:
    """A cleaned block that remains traceable to one parser output block."""

    ordinal: int
    source_ordinal: int
    text: str
    block_type: str
    page_number: int | None = None
    heading_path: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CleaningRuleHit:
    rule_id: str
    source_ordinal: int
    action: str
    before_text: str
    after_text: str | None


@dataclass(frozen=True, slots=True)
class CleaningStats:
    source_block_count: int
    cleaned_block_count: int
    removed_block_count: int
    modified_block_count: int
    source_character_count: int
    cleaned_character_count: int
    rule_hit_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class CleanResult:
    cleaning_id: str
    source_version_id: str
    cleaner_version: str
    rule_set_version: str
    text: str
    blocks: tuple[CleanedBlock, ...]
    hits: tuple[CleaningRuleHit, ...]
    stats: CleaningStats


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrieval unit with source, section, page, and neighbor provenance."""

    chunk_id: str
    chunking_id: str
    cleaning_id: str
    document_id: str
    ordinal: int
    parent_id: str
    text: str
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    source_ordinals: tuple[int, ...]
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChunkResult:
    chunking_id: str
    cleaning_id: str
    document_id: str
    chunker_version: str
    target_characters: int
    max_characters: int
    chunks: tuple[Chunk, ...]


@dataclass(frozen=True, slots=True)
class KeywordIndexResult:
    index_id: str
    chunking_id: str
    document_id: str
    indexer_version: str
    tokenizer: str
    indexed_chunk_count: int


@dataclass(frozen=True, slots=True)
class KeywordSearchResult:
    rank: int
    chunk_id: str
    document_id: str
    title: str
    text: str
    snippet: str
    score: float
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    source_uri: str | None


@dataclass(frozen=True, slots=True)
class ChunkEmbedding:
    chunk_id: str
    ordinal: int
    vector: tuple[float, ...]
    token_count: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    embedding_id: str
    chunking_id: str
    document_id: str
    embedder_version: str
    model_name: str
    model_revision: str
    dimension: int
    normalized: bool
    passage_prefix: str
    max_sequence_length: int
    embeddings: tuple[ChunkEmbedding, ...]


@dataclass(frozen=True, slots=True)
class VectorIndexMember:
    document_id: str
    chunking_id: str
    embedding_id: str
    indexed_chunk_count: int


@dataclass(frozen=True, slots=True)
class VectorIndexResult:
    vector_index_id: str
    collection_name: str
    indexer_version: str
    model_name: str
    model_revision: str
    dimension: int
    distance: str
    normalized: bool
    passage_prefix: str
    query_prefix: str
    max_sequence_length: int
    members: tuple[VectorIndexMember, ...]


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    rank: int
    vector_index_id: str
    chunk_id: str
    document_id: str
    title: str
    text: str
    score: float
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    source_uri: str | None


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    rank: int
    chunk_id: str
    document_id: str
    title: str
    text: str
    rrf_score: float
    keyword_rank: int | None
    keyword_score: float | None
    vector_rank: int | None
    vector_score: float | None
    vector_index_id: str | None
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    source_uri: str | None

    @property
    def score(self) -> float:
        return self.rrf_score


@dataclass(frozen=True, slots=True)
class ExpandedChunk:
    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    source_ordinals: tuple[int, ...]
    relation: str
    distance: int


@dataclass(frozen=True, slots=True)
class ContextExpansionResult:
    anchor: HybridSearchResult
    expanded_chunks: tuple[ExpandedChunk, ...]
    context_text: str
    context_character_count: int
    max_context_characters: int
    context_budget_exceeded: bool

    @property
    def rank(self) -> int:
        return self.anchor.rank

    @property
    def chunk_id(self) -> str:
        return self.anchor.chunk_id

    @property
    def document_id(self) -> str:
        return self.anchor.document_id

    @property
    def title(self) -> str:
        return self.anchor.title

    @property
    def text(self) -> str:
        return self.anchor.text

    @property
    def score(self) -> float:
        return self.anchor.score

    @property
    def rrf_score(self) -> float:
        return self.anchor.rrf_score

    @property
    def keyword_rank(self) -> int | None:
        return self.anchor.keyword_rank

    @property
    def keyword_score(self) -> float | None:
        return self.anchor.keyword_score

    @property
    def vector_rank(self) -> int | None:
        return self.anchor.vector_rank

    @property
    def vector_score(self) -> float | None:
        return self.anchor.vector_score

    @property
    def vector_index_id(self) -> str | None:
        return self.anchor.vector_index_id

    @property
    def heading_path(self) -> tuple[str, ...]:
        return self.anchor.heading_path

    @property
    def source_uri(self) -> str | None:
        return self.anchor.source_uri


@dataclass(frozen=True, slots=True)
class Document:
    document_id: str
    canonical_id: str
    title: str
    source_format: SourceFormat
    content_type: str
    source_path: str
    source_uri: str | None
    content_hash: str
    index_status: str = "not_indexed"


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    version_id: str
    document_id: str
    content_hash: str
    parser_version: str
    extracted_text: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IngestionRun:
    run_id: str
    source_path: str
    status: IngestionStatus
    document_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None