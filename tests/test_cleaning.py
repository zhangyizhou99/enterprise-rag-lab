from pathlib import Path

from enterprise_rag_lab.cleaning import CleaningService, clean_blocks
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import IngestionStatus, ParsedBlock
from enterprise_rag_lab.parsers import parse_document

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_clean_blocks_preserves_source_location_and_audits_each_change() -> None:
    source = (
        ParsedBlock(
            ordinal=0,
            text="  Keep\u00a0 this  ",
            page_number=7,
            heading_path=("Operations",),
        ),
        ParsedBlock(ordinal=1, text="Keep this"),
        ParsedBlock(ordinal=2, text="DRAFT - DO NOT DISTRIBUTE"),
        ParsedBlock(ordinal=3, text="Quarterly report", block_type="header"),
    )

    blocks, hits, stats = clean_blocks(source)

    assert source[0].text == "  Keep\u00a0 this  "
    assert [block.text for block in blocks] == ["Keep this"]
    assert blocks[0].source_ordinal == 0
    assert blocks[0].page_number == 7
    assert blocks[0].heading_path == ("Operations",)
    assert stats.removed_block_count == 3
    assert stats.modified_block_count == 1
    assert stats.rule_hit_counts == {
        "deduplicate_exact_paragraph": 1,
        "drop_distribution_label": 1,
        "drop_running_header_footer": 1,
        "normalize_whitespace": 1,
    }
    assert [(hit.rule_id, hit.action) for hit in hits] == [
        ("normalize_whitespace", "replace"),
        ("deduplicate_exact_paragraph", "drop"),
        ("drop_distribution_label", "drop"),
        ("drop_running_header_footer", "drop"),
    ]


def test_cleaner_does_not_drop_real_markdown_content() -> None:
    parsed = parse_document(PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md")

    blocks, hits, stats = clean_blocks(parsed.blocks)

    assert stats.source_block_count == stats.cleaned_block_count == 39
    assert stats.removed_block_count == 0
    assert all(hit.action != "drop" for hit in hits)
    assert "CORSMiddleware" in "\n".join(block.text for block in blocks)
    assert any(block.heading_path[-1:] == ("源",) for block in blocks)


def test_cleaner_removes_only_repeated_pdf_edge_lines() -> None:
    source = tuple(
        ParsedBlock(
            ordinal=page_number - 1,
            text=(
                f"Chapter {page_number}\n"
                f"Opening context {page_number}\n"
                f"Section context {page_number}\n"
                "Repeated body term\n"
                f"Unique body {page_number}\n"
                "Example Standard\n"
                f"Example Authors Page {page_number}"
            ),
            block_type="page",
            page_number=page_number,
        )
        for page_number in range(1, 6)
    )

    blocks, hits, stats = clean_blocks(source)

    assert stats.source_block_count == stats.cleaned_block_count == 5
    assert stats.removed_block_count == 0
    assert stats.rule_hit_counts["drop_repeated_pdf_boilerplate"] == 5
    assert [block.page_number for block in blocks] == [1, 2, 3, 4, 5]
    assert all("Example Standard" not in block.text for block in blocks)
    assert all("Example Authors Page" not in block.text for block in blocks)
    assert all("Repeated body term" in block.text for block in blocks)
    removed = [hit.before_text for hit in hits if hit.rule_id == "drop_repeated_pdf_boilerplate"]
    assert removed[0] == "Example Standard\nExample Authors Page 1"


def test_cleaner_removes_real_pdf_boilerplate_without_losing_pages() -> None:
    parsed = parse_document(PROJECT_ROOT / "data/raw/pdf/rfc-9112.pdf")

    blocks, hits, stats = clean_blocks(parsed.blocks)

    assert stats.source_block_count > 46
    assert stats.cleaned_block_count >= 46
    assert stats.removed_block_count == 2
    assert stats.rule_hit_counts["drop_empty_block"] == 2
    assert {block.page_number for block in blocks} == set(range(1, 47))
    assert all("Fielding, et al. Standards Track Page" not in block.text for block in blocks)
    assert all("RFC 9112 HTTP/1.1 June 2022" not in block.text for block in blocks[1:])
    assert "Message Parsing" in "\n".join(block.text for block in blocks)
    boilerplate_hits = [hit for hit in hits if hit.rule_id == "drop_repeated_pdf_boilerplate"]
    assert {
        parsed.blocks[hit.source_ordinal].page_number for hit in boilerplate_hits
    } == set(range(1, 47))
    assert all(len(hit.before_text) < 100 for hit in boilerplate_hits)


def test_cleaning_replay_is_idempotent_and_keeps_parser_output(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "ingestion.sqlite3")
    ingestion = IngestionService(store)
    source_path = PROJECT_ROOT / "data/fixtures/docx/cors-incident-postmortem-noisy.docx"
    run = ingestion.ingest(source_path)
    assert run.status is IngestionStatus.SUCCEEDED

    source = store.get_latest_parsed_version(run.document_id or "")
    assert source is not None
    source_version_id, source_blocks = source

    cleaner = CleaningService(store)
    first = cleaner.clean_document(run.document_id or "")
    second = cleaner.clean_document(run.document_id or "")

    assert first is not None
    assert second == first
    assert store.count_blocks(source_version_id) == len(source_blocks) == 20
    assert first.stats.cleaned_block_count == 12
    assert first.stats.removed_block_count == 8
    assert first.stats.rule_hit_counts["drop_running_header_footer"] == 2

    summary = store.inspect_cleaning(run.document_id or "")
    assert summary is not None
    assert summary["cleaning_id"] == first.cleaning_id
    assert summary["character_delta"] == -337
    assert len(summary["rule_hits"]) == 8

    cleaned_blocks = store.list_cleaned_blocks(run.document_id or "", limit=100)
    assert len(cleaned_blocks) == 12
    assert all(block["block_type"] not in {"header", "footer"} for block in cleaned_blocks)
    assert all("DO NOT DISTRIBUTE" not in str(block["text"]) for block in cleaned_blocks)
    table = next(block for block in cleaned_blocks if block["block_type"] == "table")
    assert "\t" in str(table["text"])