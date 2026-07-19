"""Deterministic reciprocal-rank fusion over keyword and vector retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from enterprise_rag_lab.models import (
    HybridSearchResult,
    KeywordSearchResult,
    VectorSearchResult,
)

RRF_RETRIEVER_VERSION = "0.1.0"
RRF_K = 60
DEFAULT_RRF_CANDIDATE_LIMIT = 20
RRF_RETRIEVER_ID = (
    f"rrf_bm25_vector_k{RRF_K}_c{DEFAULT_RRF_CANDIDATE_LIMIT}_"
    f"v{RRF_RETRIEVER_VERSION}"
)


class KeywordRetriever(Protocol):
    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> Sequence[KeywordSearchResult]: ...


class VectorRetriever(Protocol):
    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> Sequence[VectorSearchResult]: ...


@dataclass(slots=True)
class _FusionCandidate:
    result: KeywordSearchResult | VectorSearchResult
    keyword_rank: int | None = None
    keyword_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None
    vector_index_id: str | None = None

    @property
    def rrf_score(self) -> float:
        return sum(
            1.0 / (RRF_K + rank)
            for rank in (self.keyword_rank, self.vector_rank)
            if rank is not None
        )


def reciprocal_rank_fusion(
    keyword_results: Sequence[KeywordSearchResult],
    vector_results: Sequence[VectorSearchResult],
    limit: int,
) -> tuple[HybridSearchResult, ...]:
    if limit < 1 or limit > 100:
        raise ValueError("Search limit must be between 1 and 100")

    candidates: dict[str, _FusionCandidate] = {}
    for result in keyword_results:
        _validate_rank(result.rank)
        candidate = candidates.setdefault(
            result.chunk_id,
            _FusionCandidate(result=result),
        )
        _validate_identity(candidate.result, result)
        if candidate.keyword_rank is None or result.rank < candidate.keyword_rank:
            candidate.result = result
            candidate.keyword_rank = result.rank
            candidate.keyword_score = result.score

    for result in vector_results:
        _validate_rank(result.rank)
        candidate = candidates.setdefault(
            result.chunk_id,
            _FusionCandidate(result=result),
        )
        _validate_identity(candidate.result, result)
        if candidate.vector_rank is None or result.rank < candidate.vector_rank:
            candidate.vector_rank = result.rank
            candidate.vector_score = result.score
            candidate.vector_index_id = result.vector_index_id

    ranked = sorted(
        candidates.values(),
        key=lambda candidate: (-candidate.rrf_score, candidate.result.chunk_id),
    )[:limit]
    return tuple(
        _to_result(rank, candidate)
        for rank, candidate in enumerate(ranked, start=1)
    )


class RRFSearchService:
    def __init__(
        self,
        keyword_retriever: KeywordRetriever,
        vector_retriever: VectorRetriever,
        candidate_limit: int = DEFAULT_RRF_CANDIDATE_LIMIT,
    ) -> None:
        if candidate_limit < 1 or candidate_limit > 100:
            raise ValueError("Candidate limit must be between 1 and 100")
        self.keyword_retriever = keyword_retriever
        self.vector_retriever = vector_retriever
        self.candidate_limit = candidate_limit

    @property
    def retriever_id(self) -> str:
        return RRF_RETRIEVER_ID if self.candidate_limit == DEFAULT_RRF_CANDIDATE_LIMIT else (
            f"rrf_bm25_vector_k{RRF_K}_c{self.candidate_limit}_"
            f"v{RRF_RETRIEVER_VERSION}"
        )

    def search(self, query: str, limit: int = 5) -> tuple[HybridSearchResult, ...]:
        if not query.strip():
            raise ValueError("Hybrid query must not be blank")
        keyword_results = self.keyword_retriever.search(query, self.candidate_limit)
        vector_results = self.vector_retriever.search(query, self.candidate_limit)
        return reciprocal_rank_fusion(keyword_results, vector_results, limit)


def _validate_rank(rank: int) -> None:
    if rank < 1:
        raise ValueError("Source result ranks must be positive")


def _validate_identity(
    existing: KeywordSearchResult | VectorSearchResult,
    incoming: KeywordSearchResult | VectorSearchResult,
) -> None:
    if existing.document_id != incoming.document_id:
        raise RuntimeError(
            f"Chunk {incoming.chunk_id} has inconsistent document provenance"
        )


def _to_result(rank: int, candidate: _FusionCandidate) -> HybridSearchResult:
    result = candidate.result
    return HybridSearchResult(
        rank=rank,
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        title=result.title,
        text=result.text,
        rrf_score=candidate.rrf_score,
        keyword_rank=candidate.keyword_rank,
        keyword_score=candidate.keyword_score,
        vector_rank=candidate.vector_rank,
        vector_score=candidate.vector_score,
        vector_index_id=candidate.vector_index_id,
        heading_path=result.heading_path,
        page_start=result.page_start,
        page_end=result.page_end,
        source_uri=result.source_uri,
    )