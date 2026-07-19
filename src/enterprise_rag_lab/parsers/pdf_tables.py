"""Deterministic native-PDF table recognition and cross-page merging."""

from __future__ import annotations

import hashlib
import json
import math
import re
from bisect import bisect_right
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any, Sequence

from pdfplumber.page import Page

TABLE_RECOGNIZER_VERSION = "pdfplumber_rows_v0.1.0"

_COLUMN_CLUSTER_TOLERANCE = 3.0
_MIN_COLUMN_GAP = 18.0
_MIN_HEADER_COLUMN_GAP = 8.0
_LINE_TOLERANCE = 2.0
_PREVIOUS_PAGE_BOTTOM_RATIO = 0.75
_NEXT_PAGE_TOP_RATIO = 0.25
_NORMALIZED_COLUMN_TOLERANCE = 0.01
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class TableFragment:
    fragment_id: str
    page_number: int
    page_width: float
    page_height: float
    table_index: int
    table_count: int
    bbox: tuple[float, float, float, float]
    column_starts: tuple[float, ...]
    rows: tuple[tuple[str, ...], ...]

    @property
    def header(self) -> tuple[str, ...]:
        return self.rows[0] if self.rows else ()


@dataclass(frozen=True, slots=True)
class LogicalTable:
    table_id: str
    fragments: tuple[TableFragment, ...]
    rows: tuple[tuple[str, ...], ...]

    @property
    def page_start(self) -> int:
        return self.fragments[0].page_number

    @property
    def page_end(self) -> int:
        return self.fragments[-1].page_number

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    @property
    def text(self) -> str:
        return "\n".join(
            "\t".join(_flatten_cell(cell) for cell in row)
            for row in self.rows
        )


@dataclass(frozen=True, slots=True)
class TableRecognitionResult:
    fragments_by_page: dict[int, tuple[TableFragment, ...]]
    tables: tuple[LogicalTable, ...]
    table_by_fragment: dict[str, LogicalTable]
    warnings: tuple[str, ...]
    library_version: str


def _flatten_cell(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _word_center_in_bbox(
    word: dict[str, Any],
    bbox: tuple[float, float, float, float],
) -> bool:
    x0, top, x1, bottom = bbox
    center_x = (float(word["x0"]) + float(word["x1"])) / 2
    center_y = (float(word["top"]) + float(word["bottom"])) / 2
    return x0 <= center_x <= x1 and top <= center_y <= bottom


def _row_words(
    words: list[dict[str, Any]],
    row_bboxes: list[tuple[float, float, float, float]],
) -> list[list[dict[str, Any]]]:
    return [
        sorted(
            (word for word in words if _word_center_in_bbox(word, bbox)),
            key=lambda word: (float(word["top"]), float(word["x0"])),
        )
        for bbox in row_bboxes
    ]


def _position_clusters(
    rows: list[list[dict[str, Any]]],
) -> list[tuple[float, frozenset[int]]]:
    positions = sorted(
        (float(word["x0"]), row_index)
        for row_index, words in enumerate(rows)
        for word in words
    )
    clusters: list[tuple[list[float], set[int]]] = []
    for position, row_index in positions:
        if not clusters:
            clusters.append(([position], {row_index}))
            continue
        values, row_indexes = clusters[-1]
        center = sum(values) / len(values)
        if abs(position - center) <= _COLUMN_CLUSTER_TOLERANCE:
            values.append(position)
            row_indexes.add(row_index)
        else:
            clusters.append(([position], {row_index}))
    return [
        (sum(values) / len(values), frozenset(row_indexes))
        for values, row_indexes in clusters
    ]


def _infer_column_starts(
    rows: list[list[dict[str, Any]]],
) -> tuple[float, ...]:
    nonempty_rows = [words for words in rows if words]
    if len(nonempty_rows) < 2:
        return ()

    clusters = _position_clusters(rows)
    minimum_support = max(2, math.ceil(len(nonempty_rows) * 0.5))
    candidates: list[tuple[float, int]] = []
    header_words = sorted(nonempty_rows[0], key=lambda word: float(word["x0"]))
    possible_starts = [
        word
        for index, word in enumerate(header_words)
        if index == 0
        or float(word["x0"]) - float(header_words[index - 1]["x1"])
        >= _MIN_HEADER_COLUMN_GAP
    ]
    for header_word in possible_starts:
        header_x = float(header_word["x0"])
        center, row_indexes = min(
            clusters,
            key=lambda cluster: abs(cluster[0] - header_x),
        )
        if (
            abs(center - header_x) <= _COLUMN_CLUSTER_TOLERANCE
            and len(row_indexes) >= minimum_support
        ):
            candidates.append((center, len(row_indexes)))

    selected: list[tuple[float, int]] = []
    for candidate in sorted(set(candidates)):
        if not selected or candidate[0] - selected[-1][0] >= _MIN_COLUMN_GAP:
            selected.append(candidate)
            continue
        if candidate[1] > selected[-1][1]:
            selected[-1] = candidate

    if not 2 <= len(selected) <= 12:
        return ()
    return tuple(position for position, _ in selected)


def _render_cell(words: list[dict[str, Any]]) -> str:
    if not words:
        return ""
    lines: list[list[str]] = []
    current_line: list[str] = []
    current_top: float | None = None
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        if current_top is not None and abs(top - current_top) > _LINE_TOLERANCE:
            lines.append(current_line)
            current_line = []
        current_line.append(str(word["text"]))
        current_top = top if current_top is None else current_top
        if current_line and len(current_line) == 1:
            current_top = top
    if current_line:
        lines.append(current_line)
    return "\n".join(" ".join(line) for line in lines)


def _structure_rows(
    rows: list[list[dict[str, Any]]],
    column_starts: tuple[float, ...],
) -> tuple[tuple[str, ...], ...]:
    structured: list[tuple[str, ...]] = []
    for words in rows:
        cells: list[list[dict[str, Any]]] = [[] for _ in column_starts]
        for word in words:
            column = bisect_right(column_starts, float(word["x0"]) + 0.01) - 1
            cells[max(0, min(column, len(cells) - 1))].append(word)
        rendered = tuple(_render_cell(cell) for cell in cells)
        if any(rendered):
            structured.append(rendered)
    return tuple(structured)


def _fallback_rows(table: Any) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for row in table.extract() or []:
        rendered = tuple(_flatten_cell(cell or "") for cell in row)
        if any(rendered):
            rows.append(rendered)
    return tuple(rows)


def _detect_page_tables(page: Page, page_number: int) -> tuple[TableFragment, ...]:
    tables = page.find_tables()
    page_words = page.extract_words(x_tolerance=2, y_tolerance=2)
    fragments: list[TableFragment] = []
    for table_index, table in enumerate(tables):
        bbox = tuple(float(value) for value in table.bbox)
        words = [word for word in page_words if _word_center_in_bbox(word, bbox)]
        row_bboxes = [tuple(float(value) for value in row.bbox) for row in table.rows]
        rows_of_words = _row_words(words, row_bboxes)
        column_starts = _infer_column_starts(rows_of_words)
        rows = (
            _structure_rows(rows_of_words, column_starts)
            if column_starts
            else _fallback_rows(table)
        )
        if not rows:
            continue
        fragments.append(
            TableFragment(
                fragment_id=f"page-{page_number}-table-{table_index + 1}",
                page_number=page_number,
                page_width=float(page.width),
                page_height=float(page.height),
                table_index=table_index,
                table_count=len(tables),
                bbox=bbox,
                column_starts=column_starts,
                rows=rows,
            )
        )
    return tuple(fragments)


def _normalized_header(fragment: TableFragment) -> tuple[str, ...]:
    return tuple(_flatten_cell(cell).casefold() for cell in fragment.header)


def _has_matching_columns(previous: TableFragment, current: TableFragment) -> bool:
    if len(previous.column_starts) < 2 or len(previous.column_starts) != len(current.column_starts):
        return False
    previous_normalized = tuple(value / previous.page_width for value in previous.column_starts)
    current_normalized = tuple(value / current.page_width for value in current.column_starts)
    return all(
        abs(left - right) <= _NORMALIZED_COLUMN_TOLERANCE
        for left, right in zip(previous_normalized, current_normalized, strict=True)
    )


def _is_cross_page_continuation(
    previous: TableFragment,
    current: TableFragment,
) -> bool:
    return (
        current.page_number == previous.page_number + 1
        and previous.table_index == previous.table_count - 1
        and current.table_index == 0
        and previous.bbox[3] / previous.page_height >= _PREVIOUS_PAGE_BOTTOM_RATIO
        and current.bbox[1] / current.page_height <= _NEXT_PAGE_TOP_RATIO
        and _normalized_header(previous) == _normalized_header(current)
        and _has_matching_columns(previous, current)
    )


def _logical_table(fragments: list[TableFragment]) -> LogicalTable:
    rows = list(fragments[0].rows)
    for fragment in fragments[1:]:
        rows.extend(fragment.rows[1:])
    identity = json.dumps(
        {
            "fragments": [
                {
                    "page": fragment.page_number,
                    "bbox": [round(value, 4) for value in fragment.bbox],
                }
                for fragment in fragments
            ],
            "rows": rows,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    table_id = f"table_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
    return LogicalTable(table_id, tuple(fragments), tuple(rows))


def recognize_tables(pages: Sequence[Page]) -> TableRecognitionResult:
    """Recognize native-PDF tables and merge deterministic page continuations."""

    fragments_by_page: dict[int, tuple[TableFragment, ...]] = {}
    warnings: list[str] = []
    ordered_fragments: list[TableFragment] = []
    for page_number, page in enumerate(pages, start=1):
        try:
            fragments = _detect_page_tables(page, page_number)
        except Exception as error:
            warnings.append(
                f"Page {page_number} table recognition failed: "
                f"{type(error).__name__}: {error}"
            )
            fragments = ()
        fragments_by_page[page_number] = fragments
        ordered_fragments.extend(fragments)

    groups: list[list[TableFragment]] = []
    for fragment in ordered_fragments:
        if groups and _is_cross_page_continuation(groups[-1][-1], fragment):
            groups[-1].append(fragment)
        else:
            groups.append([fragment])

    tables = tuple(_logical_table(group) for group in groups)
    table_by_fragment = {
        fragment.fragment_id: table
        for table in tables
        for fragment in table.fragments
    }
    return TableRecognitionResult(
        fragments_by_page=fragments_by_page,
        tables=tables,
        table_by_fragment=table_by_fragment,
        warnings=tuple(warnings),
        library_version=version("pdfplumber"),
    )