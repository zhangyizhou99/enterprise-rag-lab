"""Document format detection and parser routing."""

from __future__ import annotations

from pathlib import Path

from enterprise_rag_lab.models import ParseResult, SourceFormat
from enterprise_rag_lab.parsers.base import (
    LegacyDocConversionRequired,
    UnsupportedFormatError,
)
from enterprise_rag_lab.parsers.docx import DocxParser
from enterprise_rag_lab.parsers.markdown import MarkdownParser
from enterprise_rag_lab.parsers.pdf import PdfParser

_FORMATS = {
    ".md": SourceFormat.MARKDOWN,
    ".markdown": SourceFormat.MARKDOWN,
    ".pdf": SourceFormat.PDF,
    ".docx": SourceFormat.DOCX,
    ".doc": SourceFormat.DOC,
}


def detect_source_format(path: Path) -> SourceFormat:
    try:
        return _FORMATS[path.suffix.lower()]
    except KeyError as error:
        raise UnsupportedFormatError(path) from error


def parse_document(path: str | Path) -> ParseResult:
    source_path = Path(path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    source_format = detect_source_format(source_path)
    if source_format is SourceFormat.DOC:
        raise LegacyDocConversionRequired(source_path)
    parser = {
        SourceFormat.MARKDOWN: MarkdownParser(),
        SourceFormat.PDF: PdfParser(),
        SourceFormat.DOCX: DocxParser(),
    }[source_format]
    return parser.parse(source_path)