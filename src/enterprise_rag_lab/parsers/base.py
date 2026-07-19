"""Parser interfaces and structured parsing errors."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from enterprise_rag_lab.models import ParseResult


class DocumentParser(Protocol):
    def parse(self, path: Path) -> ParseResult: ...


class DocumentParseError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class UnsupportedFormatError(DocumentParseError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            "unsupported_format",
            f"Unsupported document format: {path.suffix or '<none>'}",
        )


class LegacyDocConversionRequired(DocumentParseError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            "legacy_doc_conversion_required",
            (
                f"Legacy Word document requires LibreOffice conversion: {path}. "
                "Install it with 'winget install --id "
                "TheDocumentFoundation.LibreOffice --exact', then convert the file "
                "with soffice --headless --convert-to docx."
            ),
        )