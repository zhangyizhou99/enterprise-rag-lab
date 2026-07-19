"""Deterministic structure-aware chunking for cleaned document blocks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from enterprise_rag_lab.models import Chunk, ChunkResult, CleanedBlock

CHUNKER_VERSION = "0.4.0"
DEFAULT_TARGET_CHARACTERS = 800
DEFAULT_MAX_CHARACTERS = 900
MIN_TRAILING_CHUNK_CHARACTERS = 200

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")
_ATOMIC_BLOCK_TYPES = {"table"}


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    source_ordinal: int
    block_type: str
    page_number: int | None
    heading_path: tuple[str, ...]
    atomic: bool = False
    split_code_block: bool = False


@dataclass(frozen=True, slots=True)
class _Draft:
    text: str
    source_ordinals: tuple[int, ...]
    block_types: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    heading_path: tuple[str, ...]
    oversized_atomic_block: bool
    split_code_block: bool


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _pack_segments(segments: list[str], max_characters: int) -> list[str]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_length = 0

    for segment in segments:
        separator_length = 1 if current else 0
        if current and current_length + separator_length + len(segment) > max_characters:
            groups.append(current)
            current = []
            current_length = 0
        if len(segment) <= max_characters:
            current.append(segment)
            current_length += (1 if current_length else 0) + len(segment)
            continue

        words = segment.split()
        for word in words:
            separator_length = 1 if current else 0
            if current and current_length + separator_length + len(word) > max_characters:
                groups.append(current)
                current = []
                current_length = 0
            current.append(word)
            current_length += (1 if current_length else 0) + len(word)

    if current:
        groups.append(current)

    minimum = min(MIN_TRAILING_CHUNK_CHARACTERS, max_characters // 4)
    if len(groups) > 1 and len("\n".join(groups[-1])) < minimum:
        combined = groups[-2] + groups[-1]
        candidates: list[tuple[int, int]] = []
        for split_at in range(1, len(combined)):
            left_length = len("\n".join(combined[:split_at]))
            right_length = len("\n".join(combined[split_at:]))
            if left_length <= max_characters and right_length <= max_characters:
                candidates.append((abs(left_length - right_length), split_at))
        if candidates:
            _, split_at = min(candidates)
            groups[-2:] = [combined[:split_at], combined[split_at:]]

    return ["\n".join(group) for group in groups]


def _split_non_atomic_text(text: str, max_characters: int) -> list[str]:
    if len(text) <= max_characters:
        return [text]

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    segments: list[str] = []
    for line in lines or [text]:
        sentences = [sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(line) if sentence.strip()]
        segments.extend(sentences or [line])
    return _pack_segments(segments, max_characters)


def _split_code_text(text: str, max_characters: int) -> list[str]:
    if len(text) <= max_characters:
        return [text]

    parts: list[str] = []
    start = 0
    while len(text) - start > max_characters:
        limit = start + max_characters
        search_start = start + max_characters // 2
        newline = text.rfind("\n", search_start, limit)
        split_at = newline + 1 if newline >= search_start else limit
        parts.append(text[start:split_at])
        start = split_at
    parts.append(text[start:])

    minimum = min(MIN_TRAILING_CHUNK_CHARACTERS, max_characters // 4)
    if len(parts) > 1 and len(parts[-1]) < minimum:
        combined = parts[-2] + parts[-1]
        minimum_split = max(1, len(combined) - max_characters)
        maximum_split = min(max_characters, len(combined) - 1)
        midpoint = len(combined) // 2
        newline_splits = [
            index + 1
            for index, character in enumerate(combined)
            if character == "\n" and minimum_split <= index + 1 <= maximum_split
        ]
        split_at = (
            min(newline_splits, key=lambda candidate: abs(candidate - midpoint))
            if newline_splits
            else min(max(midpoint, minimum_split), maximum_split)
        )
        parts[-2:] = [combined[:split_at], combined[split_at:]]

    return parts


def _to_units(blocks: tuple[CleanedBlock, ...], max_characters: int) -> list[_Unit]:
    units: list[_Unit] = []
    for block in blocks:
        atomic = block.block_type in _ATOMIC_BLOCK_TYPES
        if block.block_type == "code":
            texts = _split_code_text(block.text, max_characters)
        else:
            texts = [block.text] if atomic else _split_non_atomic_text(block.text, max_characters)
        split_code_block = block.block_type == "code" and len(texts) > 1
        units.extend(
            _Unit(
                text=text,
                source_ordinal=block.source_ordinal,
                block_type=block.block_type,
                page_number=block.page_number,
                heading_path=block.heading_path,
                atomic=atomic,
                split_code_block=split_code_block,
            )
            for text in texts
            if text
        )
    return units


def _attach_heading_only_drafts(drafts: list[_Draft], max_characters: int) -> list[_Draft]:
    attached: list[_Draft] = []
    for draft in drafts:
        if attached:
            heading = attached[-1]
            same_or_child_section = (
                len(heading.heading_path) <= len(draft.heading_path)
                and draft.heading_path[: len(heading.heading_path)] == heading.heading_path
            )
            combined_length = len(heading.text) + 2 + len(draft.text)
            if (
                heading.block_types == ("heading",)
                and heading.page_start == draft.page_start
                and heading.page_end == draft.page_end
                and same_or_child_section
                and combined_length <= max_characters
            ):
                attached.pop()
                draft = _Draft(
                    text=f"{heading.text}\n\n{draft.text}",
                    source_ordinals=tuple(
                        dict.fromkeys((*heading.source_ordinals, *draft.source_ordinals))
                    ),
                    block_types=tuple(dict.fromkeys((*heading.block_types, *draft.block_types))),
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    heading_path=draft.heading_path,
                    oversized_atomic_block=(
                        heading.oversized_atomic_block or draft.oversized_atomic_block
                    ),
                    split_code_block=heading.split_code_block or draft.split_code_block,
                )
        attached.append(draft)
    return attached


def _parent_id(document_id: str, heading_path: tuple[str, ...]) -> str:
    section = "\x1f".join(heading_path) if heading_path else "<document>"
    return _stable_id("parent", f"{document_id}:{section}")


def chunk_blocks(
    document_id: str,
    cleaning_id: str,
    blocks: tuple[CleanedBlock, ...],
    target_characters: int = DEFAULT_TARGET_CHARACTERS,
    max_characters: int = DEFAULT_MAX_CHARACTERS,
) -> ChunkResult:
    """Group cleaned blocks without crossing section or page boundaries."""

    if target_characters < 1 or max_characters < target_characters:
        raise ValueError("Chunk sizes must satisfy 1 <= target_characters <= max_characters")

    chunking_identity = f"{cleaning_id}:{CHUNKER_VERSION}:{target_characters}:{max_characters}"
    chunking_id = _stable_id("chunking", chunking_identity)
    units = _to_units(blocks, max_characters)
    drafts: list[_Draft] = []
    current: list[_Unit] = []
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        if not current:
            return
        source_ordinals = tuple(dict.fromkeys(unit.source_ordinal for unit in current))
        pages = [unit.page_number for unit in current if unit.page_number is not None]
        drafts.append(
            _Draft(
                text="\n\n".join(unit.text for unit in current),
                source_ordinals=source_ordinals,
                block_types=tuple(dict.fromkeys(unit.block_type for unit in current)),
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                heading_path=current[0].heading_path,
                oversized_atomic_block=any(
                    unit.atomic and len(unit.text) > max_characters for unit in current
                ),
                split_code_block=any(unit.split_code_block for unit in current),
            )
        )
        current = []
        current_length = 0

    for unit in units:
        same_section = not current or current[0].heading_path == unit.heading_path
        same_page = not current or current[0].page_number == unit.page_number
        separator_length = 2 if current else 0
        exceeds_maximum = current_length + separator_length + len(unit.text) > max_characters
        reached_target = current_length >= target_characters
        if current and (
            not same_section
            or not same_page
            or exceeds_maximum
            or reached_target
            or unit.split_code_block
        ):
            flush()
        current.append(unit)
        current_length += (2 if current_length else 0) + len(unit.text)
        if (unit.atomic and len(unit.text) > max_characters) or unit.split_code_block:
            flush()
    flush()
    drafts = _attach_heading_only_drafts(drafts, max_characters)

    chunk_ids = tuple(
        _stable_id(
            "chunk",
            f"{chunking_id}:{ordinal}:{draft.source_ordinals}:{draft.text}",
        )
        for ordinal, draft in enumerate(drafts)
    )
    chunks = tuple(
        Chunk(
            chunk_id=chunk_ids[ordinal],
            chunking_id=chunking_id,
            cleaning_id=cleaning_id,
            document_id=document_id,
            ordinal=ordinal,
            parent_id=_parent_id(document_id, draft.heading_path),
            text=draft.text,
            heading_path=draft.heading_path,
            page_start=draft.page_start,
            page_end=draft.page_end,
            source_ordinals=draft.source_ordinals,
            previous_chunk_id=chunk_ids[ordinal - 1] if ordinal else None,
            next_chunk_id=chunk_ids[ordinal + 1] if ordinal + 1 < len(chunk_ids) else None,
            metadata={
                "block_types": list(draft.block_types),
                "oversized_atomic_block": draft.oversized_atomic_block,
                "split_code_block": draft.split_code_block,
            },
        )
        for ordinal, draft in enumerate(drafts)
    )
    return ChunkResult(
        chunking_id=chunking_id,
        cleaning_id=cleaning_id,
        document_id=document_id,
        chunker_version=CHUNKER_VERSION,
        target_characters=target_characters,
        max_characters=max_characters,
        chunks=chunks,
    )