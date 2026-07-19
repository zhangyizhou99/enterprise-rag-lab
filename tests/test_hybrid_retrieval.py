from collections.abc import Sequence

import pytest

from enterprise_rag_lab.cli import build_parser
from enterprise_rag_lab.models import KeywordSearchResult, VectorSearchResult
from enterprise_rag_lab.retrieval.hybrid import (
    DEFAULT_RRF_CANDIDATE_LIMIT,
    RRF_K,
    RRFSearchService,
    reciprocal_rank_fusion,
)


def _keyword_result(
    chunk_id: str,
    rank: int,
    score: float,
) -> KeywordSearchResult:
    return KeywordSearchResult(
        rank=rank,
        chunk_id=chunk_id,
        document_id=f"document-{chunk_id}",
        title=f"Title {chunk_id}",
        text=f"Text {chunk_id}",
        snippet=f"Snippet {chunk_id}",
        score=score,
        heading_path=("Section",),
        page_start=1,
        page_end=1,
        source_uri=f"https://example.test/{chunk_id}",
    )


def _vector_result(
    chunk_id: str,
    rank: int,
    score: float,
) -> VectorSearchResult:
    return VectorSearchResult(
        rank=rank,
        vector_index_id="vector-test",
        chunk_id=chunk_id,
        document_id=f"document-{chunk_id}",
        title=f"Title {chunk_id}",
        text=f"Text {chunk_id}",
        score=score,
        heading_path=("Section",),
        page_start=1,
        page_end=1,
        source_uri=f"https://example.test/{chunk_id}",
    )


class FakeKeywordRetriever:
    def __init__(self, results: Sequence[KeywordSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> Sequence[KeywordSearchResult]:
        self.calls.append((query, limit))
        return self.results[:limit]


class FakeVectorRetriever:
    def __init__(self, results: Sequence[VectorSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> Sequence[VectorSearchResult]:
        self.calls.append((query, limit))
        return self.results[:limit]


def test_rrf_deduplicates_and_uses_only_source_ranks() -> None:
    keyword_results = (
        _keyword_result("keyword-first", 1, -1000.0),
        _keyword_result("shared", 2, -9999.0),
        _keyword_result("z-keyword-only", 3, 999999.0),
    )
    vector_results = (
        _vector_result("vector-first", 1, -1000.0),
        _vector_result("shared", 2, -9999.0),
        _vector_result("a-vector-only", 3, 999999.0),
    )

    results = reciprocal_rank_fusion(keyword_results, vector_results, limit=5)

    assert [result.chunk_id for result in results] == [
        "shared",
        "keyword-first",
        "vector-first",
        "a-vector-only",
        "z-keyword-only",
    ]
    assert results[0].rrf_score == pytest.approx(2 / (RRF_K + 2))
    assert results[0].score == results[0].rrf_score
    assert results[0].keyword_rank == 2
    assert results[0].keyword_score == -9999.0
    assert results[0].vector_rank == 2
    assert results[0].vector_score == -9999.0
    assert results[0].vector_index_id == "vector-test"
    assert results[1].rrf_score == results[2].rrf_score
    assert results[3].rrf_score == results[4].rrf_score


def test_rrf_service_requests_fixed_candidate_depth_and_applies_final_limit() -> None:
    keyword = FakeKeywordRetriever(
        tuple(_keyword_result(f"keyword-{rank}", rank, -float(rank)) for rank in range(1, 4))
    )
    vector = FakeVectorRetriever(
        tuple(_vector_result(f"vector-{rank}", rank, 1 / rank) for rank in range(1, 4))
    )
    service = RRFSearchService(keyword, vector)

    results = service.search("how does dependency injection work?", limit=2)

    assert keyword.calls == [
        ("how does dependency injection work?", DEFAULT_RRF_CANDIDATE_LIMIT)
    ]
    assert vector.calls == [
        ("how does dependency injection work?", DEFAULT_RRF_CANDIDATE_LIMIT)
    ]
    assert len(results) == 2
    assert [result.rank for result in results] == [1, 2]
    assert service.retriever_id == "rrf_bm25_vector_k60_c20_v0.1.0"


def test_rrf_rejects_inconsistent_chunk_provenance() -> None:
    keyword = _keyword_result("shared", 1, -1.0)
    vector = _vector_result("shared", 1, 0.9)
    vector = VectorSearchResult(
        rank=vector.rank,
        vector_index_id=vector.vector_index_id,
        chunk_id=vector.chunk_id,
        document_id="different-document",
        title=vector.title,
        text=vector.text,
        score=vector.score,
        heading_path=vector.heading_path,
        page_start=vector.page_start,
        page_end=vector.page_end,
        source_uri=vector.source_uri,
    )

    with pytest.raises(RuntimeError, match="inconsistent document provenance"):
        reciprocal_rank_fusion((keyword,), (vector,), limit=1)


def test_cli_exposes_hybrid_search_and_rrf_evaluation() -> None:
    parser = build_parser()

    search = parser.parse_args(
        [
            "hybrid-search",
            "dependency injection",
            "--limit",
            "3",
            "--expand-context",
        ]
    )
    evaluation = parser.parse_args(
        [
            "evaluate-retrieval",
            "--retriever",
            "rrf-context",
            "--candidate-limit",
            "20",
        ]
    )

    assert search.command == "hybrid-search"
    assert search.limit == 3
    assert search.expand_context is True
    assert search.candidate_limit == DEFAULT_RRF_CANDIDATE_LIMIT
    assert evaluation.retriever == "rrf-context"
    assert evaluation.candidate_limit == DEFAULT_RRF_CANDIDATE_LIMIT