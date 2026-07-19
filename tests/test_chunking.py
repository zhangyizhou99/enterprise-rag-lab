from pathlib import Path

from enterprise_rag_lab.chunking import DEFAULT_MAX_CHARACTERS, chunk_blocks
from enterprise_rag_lab.chunking.service import ChunkingService
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import CleanedBlock, IngestionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_chunker_preserves_sections_sources_and_neighbors() -> None:
    blocks = (
        CleanedBlock(0, 0, "Overview", "heading", heading_path=("Overview",)),
        CleanedBlock(1, 1, "First paragraph.", "paragraph", heading_path=("Overview",)),
        CleanedBlock(2, 2, "Second paragraph.", "paragraph", heading_path=("Overview",)),
        CleanedBlock(3, 3, "Details", "heading", heading_path=("Details",)),
        CleanedBlock(4, 4, "Detailed paragraph.", "paragraph", heading_path=("Details",)),
    )

    result = chunk_blocks(
        "doc_example",
        "cleaning_example",
        blocks,
        target_characters=20,
        max_characters=60,
    )

    assert len(result.chunks) == 3
    assert [chunk.heading_path for chunk in result.chunks] == [
        ("Overview",),
        ("Overview",),
        ("Details",),
    ]
    assert result.chunks[0].source_ordinals == (0, 1)
    assert result.chunks[1].source_ordinals == (2,)
    assert result.chunks[0].previous_chunk_id is None
    assert result.chunks[0].next_chunk_id == result.chunks[1].chunk_id
    assert result.chunks[1].previous_chunk_id == result.chunks[0].chunk_id
    assert result.chunks[-1].next_chunk_id is None
    assert result.chunks[0].parent_id == result.chunks[1].parent_id
    assert result.chunks[1].parent_id != result.chunks[2].parent_id


def test_chunker_never_crosses_pdf_pages_and_splits_at_lines() -> None:
    page_text = "\n".join(f"Line {index}: " + "x" * 30 for index in range(12))
    blocks = (
        CleanedBlock(0, 4, page_text, "page", page_number=5),
        CleanedBlock(1, 5, page_text, "page", page_number=6),
    )

    result = chunk_blocks(
        "doc_pdf",
        "cleaning_pdf",
        blocks,
        target_characters=120,
        max_characters=180,
    )

    assert len(result.chunks) > 2
    assert all(chunk.page_start == chunk.page_end for chunk in result.chunks)
    assert {chunk.page_start for chunk in result.chunks} == {5, 6}
    assert all(len(chunk.text) <= 180 for chunk in result.chunks)
    assert {chunk.source_ordinals for chunk in result.chunks} == {(4,), (5,)}


def test_chunker_rebalances_a_tiny_page_tail() -> None:
    block = CleanedBlock(
        0,
        4,
        "\n".join(("A" * 80, "B" * 80, "C" * 20)),
        "page",
        page_number=5,
    )

    result = chunk_blocks(
        "doc_pdf",
        "cleaning_pdf",
        (block,),
        target_characters=120,
        max_characters=180,
    )

    assert len(result.chunks) == 2
    assert min(len(chunk.text) for chunk in result.chunks) >= 80
    assert max(len(chunk.text) for chunk in result.chunks) <= 180
    assert all(chunk.page_start == chunk.page_end == 5 for chunk in result.chunks)


def test_chunker_applies_the_calibrated_default_character_ceiling() -> None:
    block = CleanedBlock(
        0,
        4,
        "\n".join(("甲" * 450, "乙" * 450, "丙" * 300)),
        "paragraph",
        heading_path=("Token budget",),
    )

    result = chunk_blocks("doc_tokens", "cleaning_tokens", (block,))

    assert DEFAULT_MAX_CHARACTERS == 900
    assert len(result.chunks) == 2
    assert all(len(chunk.text) <= DEFAULT_MAX_CHARACTERS for chunk in result.chunks)


def test_chunker_keeps_tables_atomic_and_is_deterministic() -> None:
    table = "\n".join(f"row-{index}\tvalue-{index}" for index in range(20))
    blocks = (
        CleanedBlock(0, 7, table, "table", heading_path=("Metrics",)),
    )

    first = chunk_blocks(
        "doc_table",
        "cleaning_table",
        blocks,
        target_characters=50,
        max_characters=100,
    )
    second = chunk_blocks(
        "doc_table",
        "cleaning_table",
        blocks,
        target_characters=50,
        max_characters=100,
    )

    assert first == second
    assert len(first.chunks) == 1
    assert first.chunks[0].text == table
    assert first.chunks[0].metadata["oversized_atomic_block"] is True


def test_chunker_attaches_heading_only_section_to_first_descendant_chunk() -> None:
    blocks = (
        CleanedBlock(0, 0, "特性", "heading", heading_path=("特性",)),
        CleanedBlock(
            1,
            1,
            "FastAPI 特性",
            "heading",
            heading_path=("特性", "FastAPI 特性"),
        ),
        CleanedBlock(
            2,
            2,
            "FastAPI 提供了以下内容。",
            "paragraph",
            heading_path=("特性", "FastAPI 特性"),
        ),
    )

    result = chunk_blocks("doc_heading", "cleaning_heading", blocks)

    assert len(result.chunks) == 1
    assert result.chunks[0].text == "特性\n\nFastAPI 特性\n\nFastAPI 提供了以下内容。"
    assert result.chunks[0].heading_path == ("特性", "FastAPI 特性")
    assert result.chunks[0].source_ordinals == (0, 1, 2)


def test_chunker_splits_oversized_code_and_preserves_source_mapping() -> None:
    code = "\n".join(f"line-{index}: " + "x" * 32 for index in range(12))
    blocks = (
        CleanedBlock(0, 6, "Introduction before the code.", "paragraph", heading_path=("Example",)),
        CleanedBlock(1, 7, code, "code", heading_path=("Example",)),
        CleanedBlock(2, 8, "Explanation after the code.", "paragraph", heading_path=("Example",)),
    )

    result = chunk_blocks(
        "doc_code",
        "cleaning_code",
        blocks,
        target_characters=80,
        max_characters=100,
    )

    code_chunks = tuple(
        chunk for chunk in result.chunks if chunk.metadata["split_code_block"] is True
    )
    assert len(code_chunks) > 1
    assert all(len(chunk.text) <= 100 for chunk in code_chunks)
    assert "".join(chunk.text for chunk in code_chunks) == code
    assert all(chunk.source_ordinals == (7,) for chunk in code_chunks)
    assert all(chunk.metadata["block_types"] == ["code"] for chunk in code_chunks)
    assert all(chunk.metadata["oversized_atomic_block"] is False for chunk in code_chunks)
    assert result.chunks[0].text == "Introduction before the code."
    assert result.chunks[0].source_ordinals == (6,)
    assert result.chunks[-1].text == "Explanation after the code."
    assert result.chunks[-1].source_ordinals == (8,)


def test_chunking_service_replays_and_persists_provenance(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "ingestion.sqlite3")
    ingestion = IngestionService(store)
    source = PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    run = ingestion.ingest(source)
    assert run.status is IngestionStatus.SUCCEEDED
    cleaning = CleaningService(store).clean_document(run.document_id or "")
    assert cleaning is not None

    service = ChunkingService(store)
    first = service.chunk_document(
        run.document_id or "",
        target_characters=300,
        max_characters=500,
    )
    second = service.chunk_document(
        run.document_id or "",
        target_characters=300,
        max_characters=500,
    )

    assert first is not None
    assert second == first
    assert len(first.chunks) > 5
    summary = store.inspect_chunking(run.document_id or "")
    assert summary is not None
    assert summary["chunking_id"] == first.chunking_id
    assert summary["chunk_count"] == len(first.chunks)
    chunks = store.list_chunks(run.document_id or "", limit=200)
    assert len(chunks) == len(first.chunks)
    assert chunks[0]["previous_chunk_id"] is None
    assert chunks[-1]["next_chunk_id"] is None
    assert all(chunk["source_ordinals"] for chunk in chunks)
    assert any(chunk["heading_path"][-1:] == ["源"] for chunk in chunks)