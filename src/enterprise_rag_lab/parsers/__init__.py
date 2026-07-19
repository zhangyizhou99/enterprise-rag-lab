"""Unified document parsing API."""

from enterprise_rag_lab.parsers.base import (
    DocumentParseError,
    LegacyDocConversionRequired,
    UnsupportedFormatError,
)
from enterprise_rag_lab.parsers.registry import detect_source_format, parse_document

__all__ = [
    "DocumentParseError",
    "LegacyDocConversionRequired",
    "UnsupportedFormatError",
    "detect_source_format",
    "parse_document",
]