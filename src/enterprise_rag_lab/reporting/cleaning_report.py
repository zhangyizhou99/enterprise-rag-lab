"""Generate a human-readable Markdown report for one cleaning version."""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import ParsedBlock

_RULE_LABELS = {
    "normalize_whitespace": "规范空白",
    "drop_empty_block": "删除空块",
    "drop_running_header_footer": "删除页眉或页脚",
    "drop_distribution_label": "删除分发或草稿标签",
    "drop_download_prompt": "删除下载提示",
    "drop_unsupported_media": "删除媒体占位提示",
    "deduplicate_exact_paragraph": "删除完全重复段落",
}


def _markdown_cell(value: object, limit: int = 140) -> str:
    text = str(value).replace("\r", "").replace("\n", " ↵ ")
    if len(text) > limit:
        text = f"{text[:limit].rstrip()}..."
    return html.escape(text).replace("|", "&#124;")


def _text_preview(value: object, limit: int = 1200) -> str:
    text = str(value)
    if len(text) > limit:
        text = f"{text[:limit].rstrip()}\n\n[内容已截断，共 {len(str(value))} 个字符]"
    return html.escape(text)


def _location(block: ParsedBlock) -> str:
    parts: list[str] = []
    if block.page_number is not None:
        parts.append(f"第 {block.page_number} 页")
    if block.heading_path:
        parts.append(" > ".join(block.heading_path))
    return "；".join(parts) or "无额外定位"


def _as_dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def render_cleaning_report(
    summary: dict[str, object],
    source_blocks: tuple[ParsedBlock, ...],
    cleaned_blocks: list[dict[str, object]],
) -> str:
    hits = _as_dict_list(summary.get("rule_hits"))
    hits_by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        hits_by_source[int(hit["source_ordinal"])].append(hit)

    cleaned_by_source = {
        int(block["source_ordinal"]): block
        for block in cleaned_blocks
    }
    duplicate_groups = [
        (text, ordinals)
        for text, ordinals in (
            (text, [block.ordinal for block in source_blocks if block.text == text])
            for text, count in Counter(block.text for block in source_blocks).items()
            if text.strip() and count > 1
        )
    ]
    duplicate_groups.sort(key=lambda item: item[1][0])

    title = str(summary["title"])
    source_count = int(summary["source_block_count"])
    cleaned_count = int(summary["cleaned_block_count"])
    removed_count = int(summary["removed_block_count"])
    modified_count = int(summary["modified_block_count"])
    duplicate_block_count = sum(len(ordinals) for _, ordinals in duplicate_groups)

    lines = [
        f"# 清洗检查报告：{title}",
        "",
        "> 这是面向人工检查的摘要与对比报告。原始 JSON 仍保留给程序调试使用。",
        "",
        "## 一眼看结论",
        "",
        f"本次清洗把 **{source_count}** 个原始块变为 **{cleaned_count}** 个清洗块，"
        f"删除 **{removed_count}** 个，修改并保留 **{modified_count}** 个。",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| document_id | `{summary['document_id']}` |",
        f"| source_format | `{summary['source_format']}` |",
        f"| source_version_id | `{summary['source_version_id']}` |",
        f"| cleaning_id | `{summary['cleaning_id']}` |",
        f"| cleaner / rules | `{summary['cleaner_version']}` / `{summary['rule_set_version']}` |",
        f"| 原始块 / 清洗块 | {source_count} / {cleaned_count} |",
        f"| 删除块 / 修改块 | {removed_count} / {modified_count} |",
        f"| 字符数变化 | {summary['source_character_count']} -> {summary['cleaned_character_count']} "
        f"({int(summary['character_delta']):+d}) |",
        "",
        "## 完全重复文本",
        "",
    ]

    if duplicate_groups:
        lines.append(
            f"原始块中发现 **{len(duplicate_groups)}** 组完全相同文本，"
            f"共涉及 **{duplicate_block_count}** 个块。重复不等于一定删除，最终动作以规则命中为准。"
        )
        lines.append("")
        for text, ordinals in duplicate_groups:
            ordinal_text = ", ".join(str(ordinal) for ordinal in ordinals)
            lines.extend(
                [
                    f"### 源块 {ordinal_text}，共出现 {len(ordinals)} 次",
                    "",
                    "<pre>",
                    _text_preview(text),
                    "</pre>",
                    "",
                ]
            )
    else:
        lines.extend(["没有发现完全相同的原始块。", ""])

    lines.extend(
        [
            "## 规则命中汇总",
            "",
            "| 规则 | 含义 | 次数 |",
            "|---|---|---:|",
        ]
    )
    rule_counts = summary.get("rule_hit_counts")
    if isinstance(rule_counts, dict):
        for rule_id, count in rule_counts.items():
            lines.append(
                f"| `{rule_id}` | {_RULE_LABELS.get(str(rule_id), '未翻译规则')} | {count} |"
            )
    lines.extend(
        [
            "",
            "## 每个原始块的去向",
            "",
            "| 源块 | 类型 | 定位 | 结果 | 规则 | 原文预览 |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for block in source_blocks:
        block_hits = hits_by_source.get(block.ordinal, [])
        rules = ", ".join(str(hit["rule_id"]) for hit in block_hits) or "-"
        if any(hit.get("action") == "drop" for hit in block_hits):
            outcome = "删除"
        elif block.ordinal in cleaned_by_source and block_hits:
            outcome = "修改后保留"
        elif block.ordinal in cleaned_by_source:
            outcome = "原样保留"
        else:
            outcome = "未映射，需要检查"
        lines.append(
            f"| {block.ordinal} | `{block.block_type}` | {_markdown_cell(_location(block))} | "
            f"**{outcome}** | {_markdown_cell(rules)} | {_markdown_cell(block.text)} |"
        )

    lines.extend(["", "## 删除与修改详情", ""])
    if not hits:
        lines.extend(["本次没有规则命中。", ""])
    for hit in hits:
        source_ordinal = int(hit["source_ordinal"])
        block = next(item for item in source_blocks if item.ordinal == source_ordinal)
        action = "删除" if hit.get("action") == "drop" else "修改"
        lines.extend(
            [
                "<details>",
                f"<summary>源块 {source_ordinal}：{action}，规则 "
                f"<code>{html.escape(str(hit['rule_id']))}</code></summary>",
                "",
                f"定位：{html.escape(_location(block))}",
                "",
                "修改前：",
                "",
                "<pre>",
                _text_preview(hit.get("before_text", "")),
                "</pre>",
                "",
            ]
        )
        if hit.get("after_text") is not None:
            lines.extend(
                [
                    "修改后：",
                    "",
                    "<pre>",
                    _text_preview(hit["after_text"]),
                    "</pre>",
                    "",
                ]
            )
        lines.extend(["</details>", ""])

    lines.extend(
        [
            "## 如何继续核对",
            "",
            "```powershell",
            f".\\.venv\\Scripts\\python.exe -m enterprise_rag_lab list-blocks {summary['document_id']} --limit 200",
            f".\\.venv\\Scripts\\python.exe -m enterprise_rag_lab list-cleaned-blocks {summary['document_id']} --limit 200",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def export_cleaning_report(
    store: SQLiteIngestionStore,
    document_id: str,
    output_path: str | Path | None = None,
) -> Path | None:
    summary = store.inspect_cleaning(document_id)
    if summary is None:
        return None
    source_blocks = store.get_parsed_blocks(str(summary["source_version_id"]))
    cleaned_blocks = store.get_cleaned_blocks(str(summary["cleaning_id"]))
    destination = (
        Path(output_path)
        if output_path is not None
        else Path("data/reports") / f"cleaning-{document_id}.md"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_cleaning_report(summary, source_blocks, cleaned_blocks),
        encoding="utf-8",
    )
    return destination.resolve()