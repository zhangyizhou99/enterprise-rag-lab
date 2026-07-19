from pathlib import Path

import pytest

from enterprise_rag_lab.models import SourceFormat
from enterprise_rag_lab.parsers import LegacyDocConversionRequired, parse_document

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_markdown_parser_preserves_heading_context() -> None:
    path = PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"

    result = parse_document(path)

    assert result.source_format is SourceFormat.MARKDOWN
    assert result.title.startswith("CORS")
    assert "CORSMiddleware" in result.text
    assert any(block.heading_path[-1:] == ("源",) for block in result.blocks)


def test_pdf_parser_preserves_page_numbers() -> None:
    path = PROJECT_ROOT / "data/raw/pdf/rfc-9112.pdf"

    result = parse_document(path)

    assert result.source_format is SourceFormat.PDF
    assert result.metadata["page_count"] > 1
    assert result.blocks[0].page_number == 1
    assert "HTTP" in result.text


def test_pdf_parser_recognizes_and_merges_a_cross_page_table() -> None:
    path = PROJECT_ROOT / "data/raw/pdf/rfc-9112.pdf"

    result = parse_document(path)
    tables = [block for block in result.blocks if block.block_type == "table"]
    transfer_coding = next(
        block
        for block in tables
        if block.metadata["header"] == ["Name", "Description", "Section"]
        and block.metadata["page_start"] == 35
    )
    alpn = next(
        block
        for block in tables
        if block.metadata["page_start"] == 36
        and block.metadata["header"][0] == "Protocol"
    )

    assert result.metadata["cross_page_table_count"] == 1
    assert transfer_coding.metadata["page_end"] == 36
    assert transfer_coding.metadata["source_pages"] == [35, 36]
    assert transfer_coding.metadata["continued_across_pages"] is True
    assert transfer_coding.metadata["column_count"] == 3
    assert transfer_coding.metadata["row_count"] == 8
    assert [item["page_number"] for item in transfer_coding.metadata["bounding_boxes"]] == [
        35,
        36,
    ]
    assert transfer_coding.text.splitlines()[:3] == [
        "Name\tDescription\tSection",
        "chunked\tTransfer in a series of chunks\t7.1",
        'compress\tUNIX "compress" data format [Welch]\t7.2',
    ]
    assert "13. References" not in transfer_coding.text
    assert alpn.metadata["header"] == [
        "Protocol",
        "Identification Sequence",
        "Reference",
    ]
    assert alpn.metadata["column_count"] == 3
    page_text = "\n".join(
        block.text
        for block in result.blocks
        if block.block_type == "page" and block.page_number in {35, 36}
    )
    assert "chunked Transfer in a series of chunks 7.1" not in page_text


def test_docx_parser_extracts_tables_headers_and_footers() -> None:
    path = PROJECT_ROOT / "data/fixtures/docx/api-service-deployment-runbook.docx"

    result = parse_document(path)
    block_types = {block.block_type for block in result.blocks}

    assert result.source_format is SourceFormat.DOCX
    assert result.title == "API Service Deployment Runbook"
    assert {"table", "header", "footer"} <= block_types
    assert "DATABASE_URL" in result.text
    environment_heading = next(
        block for block in result.blocks if block.text == "3. Environment variables"
    )
    environment_table = next(block for block in result.blocks if block.block_type == "table")
    deployment_heading = next(
        block for block in result.blocks if block.text == "4. Deployment steps"
    )
    assert environment_heading.ordinal < environment_table.ordinal < deployment_heading.ordinal
    assert environment_table.heading_path == ("3. Environment variables",)


def test_legacy_doc_returns_actionable_error(tmp_path: Path) -> None:
    path = tmp_path / "legacy-document.doc"
    path.write_bytes(b"legacy DOC routing fixture")

    with pytest.raises(LegacyDocConversionRequired) as error:
        parse_document(path)

    assert error.value.code == "legacy_doc_conversion_required"
    assert "winget install" in str(error.value)