"""Deterministic and auditable cleaning rules for parsed document blocks."""

from __future__ import annotations

import re
from collections import Counter
from math import ceil

from enterprise_rag_lab.models import (
    CleanedBlock,
    CleaningRuleHit,
    CleaningStats,
    ParsedBlock,
)

CLEANER_VERSION = "0.2.0"
RULE_SET_VERSION = "2026-07-18.2"

_BLANK_LINES = re.compile(r"\n{3,}")
_HORIZONTAL_SPACE = re.compile(r"[ \t]+")
_PDF_PAGE_NUMBER_SUFFIX = re.compile(r"\bpage\s+\d+\s*$", re.IGNORECASE)
_PDF_EDGE_LINE_COUNT = 3
_PDF_MIN_REPETITION_PAGES = 3
_PDF_MIN_REPETITION_RATIO = 0.6
_DISTRIBUTION_LABEL = re.compile(
    r"^(?:draft(?:\s*-\s*do not distribute)?|confidential|internal use only)[.!]?$",
    re.IGNORECASE,
)
_DOWNLOAD_PROMPT = re.compile(
    r"^(?:download\s+(?:the\s+)?.+?\s+from\s+https?://\S+|点击.+下载.+)[.!。]?$",
    re.IGNORECASE,
)
_UNSUPPORTED_MEDIA = re.compile(
    r"^(?:your browser does not support (?:embedded )?media|"
    r"您的浏览器不支持(?:嵌入式)?媒体)[.!。]?$",
    re.IGNORECASE,
)


def _normalize_text(block: ParsedBlock) -> str:
    text = block.text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    if block.block_type == "code":
        return text.strip("\n")
    if block.block_type == "table":
        lines = [
            "\t".join(_HORIZONTAL_SPACE.sub(" ", cell).strip() for cell in line.split("\t"))
            for line in text.split("\n")
        ]
        return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    lines = [_HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def _drop_rule(block: ParsedBlock, text: str) -> str | None:
    if not text:
        return "drop_empty_block"
    if block.block_type in {"header", "footer"}:
        return "drop_running_header_footer"
    if _DISTRIBUTION_LABEL.fullmatch(text):
        return "drop_distribution_label"
    if _DOWNLOAD_PROMPT.fullmatch(text):
        return "drop_download_prompt"
    if _UNSUPPORTED_MEDIA.fullmatch(text):
        return "drop_unsupported_media"
    return None


def _pdf_line_identity(line: str) -> str:
    normalized = _HORIZONTAL_SPACE.sub(" ", line.replace("\u00a0", " ")).strip().casefold()
    return _PDF_PAGE_NUMBER_SUFFIX.sub("page <number>", normalized)


def _pdf_edge_positions(lines: list[str]) -> dict[str, set[int]]:
    nonempty = [index for index, line in enumerate(lines) if line.strip()]
    return {
        "head": set(nonempty[:_PDF_EDGE_LINE_COUNT]),
        "tail": set(nonempty[-_PDF_EDGE_LINE_COUNT:]),
    }


def _find_pdf_boilerplate(blocks: tuple[ParsedBlock, ...]) -> set[tuple[str, str]]:
    pages: dict[int, list[ParsedBlock]] = {}
    for block in blocks:
        if block.block_type == "page" and block.page_number:
            pages.setdefault(block.page_number, []).append(block)
    if len(pages) < _PDF_MIN_REPETITION_PAGES:
        return set()

    occurrences: Counter[tuple[str, str]] = Counter()
    edge_occurrences: Counter[str] = Counter()
    for page_blocks in pages.values():
        lines = [
            line
            for block in sorted(page_blocks, key=lambda item: item.ordinal)
            for line in _normalize_text(block).splitlines()
        ]
        positions = _pdf_edge_positions(lines)
        page_candidates = {
            (zone, _pdf_line_identity(lines[index]))
            for zone, indexes in positions.items()
            for index in indexes
            if _pdf_line_identity(lines[index])
        }
        occurrences.update(page_candidates)
        edge_occurrences.update({identity for _, identity in page_candidates})

    threshold = max(
        _PDF_MIN_REPETITION_PAGES,
        ceil(len(pages) * _PDF_MIN_REPETITION_RATIO),
    )
    candidates = {
        candidate for candidate, count in occurrences.items() if count >= threshold
    }
    candidates.update(
        ("edge", identity)
        for identity, count in edge_occurrences.items()
        if count >= threshold
    )
    return candidates


def _remove_pdf_boilerplate(
    text: str,
    candidates: set[tuple[str, str]],
    allowed_zones: set[str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    if not candidates:
        return text, ()

    lines = text.splitlines()
    positions = _pdf_edge_positions(lines)
    removable = {
        index
        for zone, indexes in positions.items()
        if allowed_zones is None or zone in allowed_zones
        for index in indexes
        if (
            (zone, _pdf_line_identity(lines[index])) in candidates
            or ("edge", _pdf_line_identity(lines[index])) in candidates
        )
    }
    removed = tuple(lines[index] for index in sorted(removable))
    retained = [line for index, line in enumerate(lines) if index not in removable]
    return "\n".join(retained).strip(), removed


def clean_blocks(
    blocks: tuple[ParsedBlock, ...],
) -> tuple[tuple[CleanedBlock, ...], tuple[CleaningRuleHit, ...], CleaningStats]:
    """Apply the versioned rule set without mutating parser output."""

    cleaned: list[CleanedBlock] = []
    hits: list[CleaningRuleHit] = []
    seen_paragraphs: set[str] = set()
    modified_ordinals: set[int] = set()
    pdf_boilerplate = _find_pdf_boilerplate(blocks)

    for block in blocks:
        text = _normalize_text(block)
        if text != block.text:
            hits.append(
                CleaningRuleHit(
                    rule_id="normalize_whitespace",
                    source_ordinal=block.ordinal,
                    action="replace",
                    before_text=block.text,
                    after_text=text,
                )
            )
            modified_ordinals.add(block.ordinal)

        if block.block_type == "page":
            segment_index = block.metadata.get("page_segment_index")
            segment_count = block.metadata.get("page_segment_count")
            allowed_zones: set[str] | None = None
            if isinstance(segment_index, int) and isinstance(segment_count, int):
                allowed_zones = set()
                if segment_index == 0:
                    allowed_zones.add("head")
                if segment_index == segment_count - 1:
                    allowed_zones.add("tail")
            text, removed_lines = _remove_pdf_boilerplate(
                text,
                pdf_boilerplate,
                allowed_zones,
            )
            if removed_lines:
                hits.append(
                    CleaningRuleHit(
                        rule_id="drop_repeated_pdf_boilerplate",
                        source_ordinal=block.ordinal,
                        action="remove_lines",
                        before_text="\n".join(removed_lines),
                        after_text=None,
                    )
                )
                modified_ordinals.add(block.ordinal)

        drop_rule = _drop_rule(block, text)
        if drop_rule is not None:
            hits.append(
                CleaningRuleHit(
                    rule_id=drop_rule,
                    source_ordinal=block.ordinal,
                    action="drop",
                    before_text=text,
                    after_text=None,
                )
            )
            continue

        paragraph_identity = text.casefold()
        if block.block_type == "paragraph" and paragraph_identity in seen_paragraphs:
            hits.append(
                CleaningRuleHit(
                    rule_id="deduplicate_exact_paragraph",
                    source_ordinal=block.ordinal,
                    action="drop",
                    before_text=text,
                    after_text=None,
                )
            )
            continue
        if block.block_type == "paragraph":
            seen_paragraphs.add(paragraph_identity)

        cleaned.append(
            CleanedBlock(
                ordinal=len(cleaned),
                source_ordinal=block.ordinal,
                text=text,
                block_type=block.block_type,
                page_number=block.page_number,
                heading_path=block.heading_path,
                metadata=dict(block.metadata),
            )
        )

    source_text = "\n\n".join(block.text for block in blocks)
    cleaned_text = "\n\n".join(block.text for block in cleaned)
    hit_counts = Counter(hit.rule_id for hit in hits)
    stats = CleaningStats(
        source_block_count=len(blocks),
        cleaned_block_count=len(cleaned),
        removed_block_count=len(blocks) - len(cleaned),
        modified_block_count=sum(block.source_ordinal in modified_ordinals for block in cleaned),
        source_character_count=len(source_text),
        cleaned_character_count=len(cleaned_text),
        rule_hit_counts=dict(sorted(hit_counts.items())),
    )
    return tuple(cleaned), tuple(hits), stats