"""Markdown parser that preserves heading ancestry and fenced code blocks."""

from __future__ import annotations

import re
from pathlib import Path

from enterprise_rag_lab.models import ParsedBlock, ParseResult, SourceFormat

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+\{[^}]+\})?\s*$")


class MarkdownParser:
    def parse(self, path: Path) -> ParseResult:
        raw_text = path.read_text(encoding="utf-8-sig")
        blocks: list[ParsedBlock] = []
        heading_stack: list[str] = []
        paragraph: list[str] = []
        code_lines: list[str] = []
        in_code_block = False
        title = path.stem

        def append_block(text: str, block_type: str) -> None:
            normalized = text.strip("\n")
            if not normalized.strip():
                return
            blocks.append(
                ParsedBlock(
                    ordinal=len(blocks),
                    text=normalized,
                    block_type=block_type,
                    heading_path=tuple(heading_stack),
                )
            )

        def flush_paragraph() -> None:
            if paragraph:
                append_block("\n".join(paragraph), "paragraph")
                paragraph.clear()

        for line in raw_text.splitlines():
            if line.startswith("```"):
                if in_code_block:
                    append_block("\n".join(code_lines), "code")
                    code_lines.clear()
                else:
                    flush_paragraph()
                in_code_block = not in_code_block
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            heading_match = _HEADING.match(line)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                heading = heading_match.group(2).strip()
                heading_stack[level - 1 :] = [heading]
                if level == 1:
                    title = heading
                append_block(heading, "heading")
            elif line.strip():
                paragraph.append(line)
            else:
                flush_paragraph()

        flush_paragraph()
        if code_lines:
            append_block("\n".join(code_lines), "code")

        return ParseResult(
            source_path=path,
            source_format=SourceFormat.MARKDOWN,
            title=title,
            text="\n\n".join(block.text for block in blocks),
            blocks=tuple(blocks),
            warnings=("Unclosed fenced code block",) if in_code_block else (),
            metadata={"encoding": "utf-8"},
        )