from collections.abc import Sequence

import pytest

from enterprise_rag_lab.models import Chunk, HybridSearchResult
from enterprise_rag_lab.retrieval.context import ContextExpansionService


def _chunk(
    chunk_id: str,
    ordinal: int,
    text: str,
    parent_id: str = "parent-section",
    heading_path: tuple[str, ...] | None = None,
    page_start: int | None = None,
    previous_chunk_id: str | None = None,
    next_chunk_id: str | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        chunking_id="chunking-current",
        cleaning_id="cleaning-current",
        document_id="document-current",
        ordinal=ordinal,
        parent_id=parent_id,
        text=text,
        heading_path=heading_path or (parent_id,),
        page_start=page_start,
        page_end=page_start,
        source_ordinals=(ordinal,),
        previous_chunk_id=previous_chunk_id,
        next_chunk_id=next_chunk_id,
    )


def _anchor(chunk_id: str, rank: int, text: str) -> HybridSearchResult:
    return HybridSearchResult(
        rank=rank,
        chunk_id=chunk_id,
        document_id="document-current",
        title="Current document",
        text=text,
        rrf_score=0.03,
        keyword_rank=2,
        keyword_score=8.0,
        vector_rank=3,
        vector_score=0.9,
        vector_index_id="vector-current",
        heading_path=("parent-section",),
        page_start=None,
        page_end=None,
        source_uri="https://example.test/current",
    )


class FakeStore:
    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = tuple(chunks)
        self.calls: list[str] = []

    def get_latest_chunks(
        self,
        document_id: str,
    ) -> tuple[str, tuple[Chunk, ...]] | None:
        self.calls.append(document_id)
        return "chunking-current", self.chunks


class FakeRetriever:
    retriever_id = "rrf-test"

    def __init__(self, anchors: Sequence[HybridSearchResult]) -> None:
        self.anchors = tuple(anchors)

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> Sequence[HybridSearchResult]:
        return self.anchors[:limit]


def test_context_expansion_preserves_anchor_rank_and_stays_in_section() -> None:
    chunks = (
        _chunk("previous", 0, "Previous evidence", next_chunk_id="anchor"),
        _chunk(
            "anchor",
            1,
            "Anchor evidence",
            previous_chunk_id="previous",
            next_chunk_id="other-section",
        ),
        _chunk(
            "other-section",
            2,
            "Unrelated section",
            parent_id="parent-other",
            previous_chunk_id="anchor",
        ),
    )
    store = FakeStore(chunks)
    service = ContextExpansionService(
        store,
        FakeRetriever((_anchor("anchor", 3, "Anchor evidence"),)),
    )

    results = service.search("question", limit=5)

    assert len(results) == 1
    assert results[0].rank == 3
    assert results[0].chunk_id == "anchor"
    assert [chunk.chunk_id for chunk in results[0].expanded_chunks] == ["previous"]
    assert results[0].expanded_chunks[0].relation == "previous"
    assert results[0].expanded_chunks[0].distance == 1
    assert results[0].context_text == "Previous evidence\n\nAnchor evidence"
    assert results[0].context_character_count == len(results[0].context_text)
    assert results[0].context_budget_exceeded is False
    assert service.retriever_id == "rrf-test_context_section_d1_b2400_v0.2.0"


def test_context_expansion_skips_oversized_neighbor_but_tries_other_side() -> None:
    chunks = (
        _chunk("previous", 0, "too long", next_chunk_id="anchor"),
        _chunk(
            "anchor",
            1,
            "anchor",
            previous_chunk_id="previous",
            next_chunk_id="next",
        ),
        _chunk("next", 2, "x", previous_chunk_id="anchor"),
    )
    service = ContextExpansionService(
        FakeStore(chunks),
        FakeRetriever((_anchor("anchor", 1, "anchor"),)),
        max_context_characters=9,
    )

    result = service.search("question", limit=1)[0]

    assert [chunk.chunk_id for chunk in result.expanded_chunks] == ["next"]
    assert result.context_text == "anchor\n\nx"
    assert result.context_character_count == 9


def test_context_expansion_rejects_stale_anchor() -> None:
    service = ContextExpansionService(
        FakeStore((_chunk("current", 0, "Current text"),)),
        FakeRetriever((_anchor("stale", 1, "Stale text"),)),
    )

    with pytest.raises(RuntimeError, match="is not a current chunk"):
        service.search("question", limit=1)


@pytest.mark.parametrize(
    ("anchor_path", "neighbor_path"),
    [
        (("Dependencies",), ("Dependencies", "What is dependency injection")),
        (("Path parameters", "Validation"), ("Path parameters", "Summary")),
    ],
)
def test_context_expansion_accepts_parent_child_and_sibling_sections(
    anchor_path: tuple[str, ...],
    neighbor_path: tuple[str, ...],
) -> None:
    chunks = (
        _chunk(
            "anchor",
            0,
            "Anchor evidence",
            parent_id="parent-anchor",
            heading_path=anchor_path,
            next_chunk_id="neighbor",
        ),
        _chunk(
            "neighbor",
            1,
            "Neighbor evidence",
            parent_id="parent-neighbor",
            heading_path=neighbor_path,
            previous_chunk_id="anchor",
        ),
    )
    service = ContextExpansionService(
        FakeStore(chunks),
        FakeRetriever((_anchor("anchor", 1, "Anchor evidence"),)),
    )

    result = service.search("question", limit=1)[0]

    assert [chunk.chunk_id for chunk in result.expanded_chunks] == ["neighbor"]


def test_context_expansion_does_not_cross_pdf_page_boundary() -> None:
    chunks = (
        _chunk(
            "anchor",
            0,
            "Page one",
            heading_path=("RFC",),
            page_start=1,
            next_chunk_id="next-page",
        ),
        _chunk(
            "next-page",
            1,
            "Page two",
            heading_path=("RFC",),
            page_start=2,
            previous_chunk_id="anchor",
        ),
    )
    service = ContextExpansionService(
        FakeStore(chunks),
        FakeRetriever((_anchor("anchor", 1, "Page one"),)),
    )

    result = service.search("question", limit=1)[0]

    assert result.expanded_chunks == ()


def test_context_expansion_deduplicates_neighbors_across_anchors() -> None:
    chunks = (
        _chunk("first", 0, "First anchor", next_chunk_id="shared"),
        _chunk(
            "shared",
            1,
            "Shared context",
            previous_chunk_id="first",
            next_chunk_id="second",
        ),
        _chunk("second", 2, "Second anchor", previous_chunk_id="shared"),
    )
    store = FakeStore(chunks)
    service = ContextExpansionService(
        store,
        FakeRetriever(
            (
                _anchor("first", 1, "First anchor"),
                _anchor("second", 2, "Second anchor"),
            )
        ),
    )

    results = service.search("question", limit=2)

    assert [chunk.chunk_id for chunk in results[0].expanded_chunks] == ["shared"]
    assert results[1].expanded_chunks == ()
    assert store.calls == ["document-current"]