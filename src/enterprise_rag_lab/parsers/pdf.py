"""PDF parser with page-addressable text and native table output."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from enterprise_rag_lab.models import ParsedBlock, ParseResult, SourceFormat
from enterprise_rag_lab.parsers.pdf_tables import (
    TABLE_RECOGNIZER_VERSION,
    LogicalTable,
    TableFragment,
    recognize_tables,
)


def _rounded_bbox(bbox: tuple[float, float, float, float]) -> list[float]:
    return [round(value, 4) for value in bbox]


def _table_metadata(table: LogicalTable, library_version: str) -> dict[str, object]:
    return {
        "table_id": table.table_id,
        "page_start": table.page_start,
        "page_end": table.page_end,
        "source_pages": [fragment.page_number for fragment in table.fragments],
        "bounding_boxes": [
            {
                "page_number": fragment.page_number,
                "bbox": _rounded_bbox(fragment.bbox),
                "normalized_bbox": [
                    round(fragment.bbox[0] / fragment.page_width, 6),
                    round(fragment.bbox[1] / fragment.page_height, 6),
                    round(fragment.bbox[2] / fragment.page_width, 6),
                    round(fragment.bbox[3] / fragment.page_height, 6),
                ],
            }
            for fragment in table.fragments
        ],
        "column_starts": [round(value, 4) for value in table.fragments[0].column_starts],
        "column_count": table.column_count,
        "row_count": len(table.rows),
        "header": [cell.replace("\n", " ") for cell in table.rows[0]],
        "continued_across_pages": len(table.fragments) > 1,
        "recognition_scope": "native_text_pdf",
        "recognizer": "pdfplumber",
        "recognizer_version": TABLE_RECOGNIZER_VERSION,
        "recognizer_library_version": library_version,
    }


def _extract_region_text(
    page: pdfplumber.page.Page,
    top: float,
    bottom: float,
) -> str:
    if bottom - top < 1:
        return ""
    region = page.crop((0, max(0.0, top), float(page.width), min(float(page.height), bottom)))
    return (region.extract_text() or "").strip()


def _append_table_page_blocks(
    blocks: list[ParsedBlock],
    page: pdfplumber.page.Page,
    page_number: int,
    fragments: tuple[TableFragment, ...],
    table_by_fragment: dict[str, LogicalTable],
    library_version: str,
) -> None:
    events: list[tuple[str, object, tuple[float, float, float, float] | None]] = []
    cursor = 0.0
    for fragment in fragments:
        text = _extract_region_text(page, cursor, fragment.bbox[1])
        if text:
            events.append(
                (
                    "page",
                    text,
                    (0.0, cursor, float(page.width), fragment.bbox[1]),
                )
            )
        table = table_by_fragment[fragment.fragment_id]
        if table.fragments[0].fragment_id == fragment.fragment_id:
            events.append(("table", table, None))
        cursor = max(cursor, fragment.bbox[3])

    text = _extract_region_text(page, cursor, float(page.height))
    if text:
        events.append(
            (
                "page",
                text,
                (0.0, cursor, float(page.width), float(page.height)),
            )
        )

    segment_count = sum(event_type == "page" for event_type, _, _ in events)
    segment_index = 0
    for event_type, value, bbox in events:
        if event_type == "table":
            table = value
            assert isinstance(table, LogicalTable)
            blocks.append(
                ParsedBlock(
                    ordinal=len(blocks),
                    text=table.text,
                    block_type="table",
                    page_number=table.page_start,
                    metadata=_table_metadata(table, library_version),
                )
            )
            continue

        assert isinstance(value, str)
        assert bbox is not None
        blocks.append(
            ParsedBlock(
                ordinal=len(blocks),
                text=value,
                block_type="page",
                page_number=page_number,
                metadata={
                    "page_segment_index": segment_index,
                    "page_segment_count": segment_count,
                    "bbox": _rounded_bbox(bbox),
                    "table_aware": True,
                },
            )
        )
        segment_index += 1


class PdfParser:
    def parse(self, path: Path) -> ParseResult:
        reader = PdfReader(path)
        blocks: list[ParsedBlock] = []
        warnings: list[str] = []
        with pdfplumber.open(path) as pdf:
            recognition = recognize_tables(pdf.pages)
            warnings.extend(recognition.warnings)
            if len(pdf.pages) != len(reader.pages):
                warnings.append(
                    "PDF page count differs between pypdf and pdfplumber: "
                    f"{len(reader.pages)} != {len(pdf.pages)}"
                )

            for page_number, pypdf_page in enumerate(reader.pages, start=1):
                fragments = recognition.fragments_by_page.get(page_number, ())
                before_count = len(blocks)
                if fragments and page_number <= len(pdf.pages):
                    _append_table_page_blocks(
                        blocks,
                        pdf.pages[page_number - 1],
                        page_number,
                        fragments,
                        recognition.table_by_fragment,
                        recognition.library_version,
                    )
                else:
                    text = (pypdf_page.extract_text() or "").strip()
                    if text:
                        blocks.append(
                            ParsedBlock(
                                ordinal=len(blocks),
                                text=text,
                                block_type="page",
                                page_number=page_number,
                                metadata={
                                    "page_segment_index": 0,
                                    "page_segment_count": 1,
                                    "table_aware": False,
                                },
                            )
                        )
                if len(blocks) == before_count and not fragments:
                    warnings.append(f"Page {page_number} has no extractable text")

        metadata = reader.metadata or {}
        title = str(metadata.get("/Title") or path.stem).strip()
        cross_page_table_count = sum(
            len(table.fragments) > 1 for table in recognition.tables
        )
        return ParseResult(
            source_path=path,
            source_format=SourceFormat.PDF,
            title=title,
            text="\n\n".join(block.text for block in blocks),
            blocks=tuple(blocks),
            warnings=tuple(warnings),
            metadata={
                "page_count": len(reader.pages),
                "table_count": len(recognition.tables),
                "table_fragment_count": sum(
                    len(fragments)
                    for fragments in recognition.fragments_by_page.values()
                ),
                "cross_page_table_count": cross_page_table_count,
                "table_recognizer_version": TABLE_RECOGNIZER_VERSION,
            },
        )