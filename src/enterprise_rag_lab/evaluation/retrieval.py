"""Versioned retrieval judgments and deterministic ranking metrics."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore

EVALUATION_SCHEMA_VERSION = "1.0"
EVALUATION_CATEGORIES = frozenset(
    {"configuration", "concept", "procedure", "troubleshooting", "comparison"}
)
REVIEW_STATUSES = frozenset({"needs_human_review", "approved"})


@dataclass(frozen=True, slots=True)
class RelevanceJudgment:
    document_id: str
    chunk_id: str
    relevance: int
    evidence_quote: str


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    query_id: str
    query: str
    category: str
    review_status: str
    judgments: tuple[RelevanceJudgment, ...]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationSet:
    evaluation_set_id: str
    schema_version: str
    corpus_snapshot: str
    annotation_policy: str
    questions: tuple[EvaluationQuery, ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class QueryEvaluation:
    query_id: str
    query: str
    category: str
    review_status: str
    candidates: tuple[EvaluationCandidate, ...]
    relevant_chunk_ids: tuple[str, ...]
    first_relevant_rank: int | None
    hit_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    first_expanded_evidence_rank: int | None
    expanded_evidence_hit_at_k: float
    expanded_evidence_recall_at_k: float
    expanded_evidence_reciprocal_rank: float
    expanded_chunk_count: int
    context_character_count: int
    unjudged_expanded_chunk_count: int
    context_budget_exceeded_count: int
    latency_ms: float


@dataclass(frozen=True, slots=True)
class EvaluationExpandedChunk:
    chunk_id: str
    document_id: str
    ordinal: int
    relation: str
    distance: int
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None


@dataclass(frozen=True, slots=True)
class EvaluationCandidate:
    rank: int
    chunk_id: str
    document_id: str
    score: float | None
    rrf_score: float | None
    keyword_rank: int | None
    keyword_score: float | None
    vector_rank: int | None
    vector_score: float | None
    vector_index_id: str | None
    title: str | None
    heading_path: tuple[str, ...]
    source_uri: str | None
    expanded_chunks: tuple[EvaluationExpandedChunk, ...]
    context_text: str | None
    context_character_count: int | None
    max_context_characters: int | None
    context_budget_exceeded: bool


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationReport:
    evaluation_set_id: str
    evaluation_set_hash: str
    corpus_snapshot: str
    retriever: str
    limit: int
    query_count: int
    approved_query_count: int
    is_provisional: bool
    hit_rate_at_k: float
    recall_at_k: float
    mrr: float
    expanded_evidence_hit_rate_at_k: float
    expanded_evidence_recall_at_k: float
    expanded_evidence_mrr: float
    mean_expanded_chunk_count: float
    mean_context_characters: float
    p95_context_characters: int
    unjudged_expansion_rate: float
    context_budget_exceeded_count: int
    mean_latency_ms: float
    p95_latency_ms: float
    queries: tuple[QueryEvaluation, ...]


class RankedResult(Protocol):
    chunk_id: str
    document_id: str


class Retriever(Protocol):
    def search(self, query: str, limit: int) -> Sequence[RankedResult]: ...


def load_evaluation_set(path: str | Path) -> RetrievalEvaluationSet:
    source = Path(path)
    raw = source.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid evaluation JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("Evaluation set root must be a JSON object")
    if payload.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported evaluation schema: {payload.get('schema_version')!r}"
        )
    questions_payload = payload.get("questions")
    if not isinstance(questions_payload, list) or not questions_payload:
        raise ValueError("Evaluation set must contain at least one question")

    questions = tuple(_load_query(item) for item in questions_payload)
    query_ids = [question.query_id for question in questions]
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("Evaluation query IDs must be unique")
    return RetrievalEvaluationSet(
        evaluation_set_id=_required_string(payload, "evaluation_set_id"),
        schema_version=EVALUATION_SCHEMA_VERSION,
        corpus_snapshot=_required_string(payload, "corpus_snapshot"),
        annotation_policy=_required_string(payload, "annotation_policy"),
        questions=questions,
        content_hash=hashlib.sha256(raw).hexdigest(),
    )


def validate_evaluation_set(
    dataset: RetrievalEvaluationSet,
    store: SQLiteIngestionStore,
    require_approved: bool = False,
) -> dict[str, object]:
    latest_chunks: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    vector_index = store.inspect_vector_index()
    if (
        vector_index is not None
        and dataset.corpus_snapshot != vector_index["vector_index_id"]
    ):
        errors.append(
            f"corpus snapshot {dataset.corpus_snapshot} does not match current "
            f"vector index {vector_index['vector_index_id']}"
        )
    for question in dataset.questions:
        if require_approved and question.review_status != "approved":
            errors.append(f"{question.query_id}: is not approved")
        for judgment in question.judgments:
            document_chunks = latest_chunks.get(judgment.document_id)
            if document_chunks is None:
                source = store.get_latest_chunks(judgment.document_id)
                document_chunks = (
                    {chunk.chunk_id: chunk.text for chunk in source[1]}
                    if source is not None
                    else {}
                )
                latest_chunks[judgment.document_id] = document_chunks
            text = document_chunks.get(judgment.chunk_id)
            if text is None:
                errors.append(
                    f"{question.query_id}: {judgment.chunk_id} is not a latest chunk "
                    f"of {judgment.document_id}"
                )
            elif judgment.evidence_quote not in text:
                errors.append(
                    f"{question.query_id}: evidence quote is absent from "
                    f"{judgment.chunk_id}"
                )
    if errors:
        raise ValueError("Evaluation set validation failed:\n" + "\n".join(errors))
    return {
        "evaluation_set_id": dataset.evaluation_set_id,
        "content_hash": dataset.content_hash,
        "question_count": len(dataset.questions),
        "judgment_count": sum(len(item.judgments) for item in dataset.questions),
        "approved_question_count": sum(
            item.review_status == "approved" for item in dataset.questions
        ),
        "needs_human_review_count": sum(
            item.review_status == "needs_human_review" for item in dataset.questions
        ),
        "corpus_snapshot": dataset.corpus_snapshot,
    }


def render_review_markdown(
    dataset: RetrievalEvaluationSet,
    store: SQLiteIngestionStore,
    start: int = 1,
    limit: int = 5,
) -> str:
    if start < 1:
        raise ValueError("Review start must be at least 1")
    if limit < 1 or limit > 30:
        raise ValueError("Review limit must be between 1 and 30")
    validate_evaluation_set(dataset, store)
    selected = dataset.questions[start - 1 : start - 1 + limit]
    if not selected:
        raise ValueError("Review start is beyond the evaluation set")

    end = start + len(selected) - 1
    lines = [
        f"# {dataset.evaluation_set_id} 人工审核 {start}-{end}",
        "",
        f"- 语料快照：`{dataset.corpus_snapshot}`",
        f"- 数据集哈希：`{dataset.content_hash}`",
        f"- 本批题数：{len(selected)}",
        "- 说明：以下相关度是种子建议，不是人工结论。逐题确认后才能将 `review_status` 改为 `approved`。",
        "- 审核对象：本阶段只评估“问题 → Chunk”的检索相关性，尚未生成答案。请判断完整 Chunk 是否含有足以支撑回答的事实，不需要撰写标准答案、查找 ID 或自行搜索语料库。",
        "",
        "相关度口径：`3` 直接完整回答；`2` 部分回答或重要辅助证据；`1` 弱相关；不相关则删除该 judgment。",
        "",
    ]
    for question in selected:
        lines.extend(
            [
                f"## {question.query_id} · {question.category}",
                "",
                f"**问题**：{question.query}",
                "",
                f"**当前状态**：`{question.review_status}`",
                "",
                "- [ ] 问题自然且含义明确",
                "- [ ] 完整 Chunk 含有足以支撑回答的事实",
                "- [ ] 相关度等级合理",
                "- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库",
                "- 决定：`通过 / 修改 / 删除`",
                "",
            ]
        )
        for ordinal, judgment in enumerate(question.judgments, start=1):
            source = store.get_latest_chunks(judgment.document_id)
            if source is None:
                raise ValueError(f"No latest chunks for {judgment.document_id}")
            chunk = next(
                item for item in source[1] if item.chunk_id == judgment.chunk_id
            )
            document = store.get_document(judgment.document_id)
            if document is None:
                raise ValueError(f"Unknown document: {judgment.document_id}")
            location = " > ".join(chunk.heading_path) or "（无标题路径）"
            if chunk.page_start is not None:
                location += f"；页码 {chunk.page_start}"
                if chunk.page_end != chunk.page_start:
                    location += f"-{chunk.page_end}"
            source_reference = document.source_uri or document.source_path
            lines.extend(
                [
                    f"### 候选证据 {ordinal}",
                    "",
                    f"- 建议相关度：`{judgment.relevance}`",
                    f"- 文档：{document.title}",
                    f"- 标题路径：{location}",
                    f"- `document_id`：`{judgment.document_id}`",
                    f"- `chunk_id`：`{judgment.chunk_id}`",
                    f"- 来源：{source_reference}",
                    "",
                    "**证据摘录**",
                    "",
                    _fenced_markdown(judgment.evidence_quote),
                    "",
                    "**当前完整 Chunk**",
                    "",
                    _fenced_markdown(chunk.text),
                    "",
                ]
            )
        if question.notes:
            lines.extend([f"**备注**：{question.notes}", ""])
        lines.extend(["---", ""])
    return "\n".join(lines).rstrip() + "\n"


class RetrievalEvaluationService:
    def evaluate(
        self,
        dataset: RetrievalEvaluationSet,
        retriever: Retriever,
        retriever_name: str,
        limit: int = 5,
    ) -> RetrievalEvaluationReport:
        if limit < 1 or limit > 100:
            raise ValueError("Evaluation limit must be between 1 and 100")
        query_results: list[QueryEvaluation] = []
        for question in dataset.questions:
            started_at = time.perf_counter()
            ranked = tuple(retriever.search(question.query, limit))
            latency_ms = (time.perf_counter() - started_at) * 1000
            relevant = {judgment.chunk_id for judgment in question.judgments}
            retrieved = tuple(result.chunk_id for result in ranked)
            expanded_by_rank = tuple(
                {
                    result.chunk_id,
                    *(
                        chunk.chunk_id
                        for chunk in getattr(result, "expanded_chunks", ())
                    ),
                }
                for result in ranked
            )
            expanded_retrieved = set().union(*expanded_by_rank) if ranked else set()
            relevant_ranks = [
                rank
                for rank, chunk_id in enumerate(retrieved, start=1)
                if chunk_id in relevant
            ]
            first_rank = min(relevant_ranks, default=None)
            retrieved_relevant = len(set(retrieved) & relevant)
            expanded_relevant_ranks = [
                rank
                for rank, chunk_ids in enumerate(expanded_by_rank, start=1)
                if chunk_ids & relevant
            ]
            first_expanded_rank = min(expanded_relevant_ranks, default=None)
            expanded_chunks = tuple(
                chunk
                for result in ranked
                for chunk in getattr(result, "expanded_chunks", ())
            )
            context_character_count = sum(
                _optional_int(getattr(result, "context_character_count", None)) or 0
                for result in ranked
            )
            budget_exceeded_count = sum(
                bool(getattr(result, "context_budget_exceeded", False))
                for result in ranked
            )
            query_results.append(
                QueryEvaluation(
                    query_id=question.query_id,
                    query=question.query,
                    category=question.category,
                    review_status=question.review_status,
                    candidates=tuple(
                        EvaluationCandidate(
                            rank=rank,
                            chunk_id=result.chunk_id,
                            document_id=result.document_id,
                            score=_optional_float(getattr(result, "score", None)),
                            rrf_score=_optional_float(
                                getattr(result, "rrf_score", None)
                            ),
                            keyword_rank=_optional_int(
                                getattr(result, "keyword_rank", None)
                            ),
                            keyword_score=_optional_float(
                                getattr(result, "keyword_score", None)
                            ),
                            vector_rank=_optional_int(
                                getattr(result, "vector_rank", None)
                            ),
                            vector_score=_optional_float(
                                getattr(result, "vector_score", None)
                            ),
                            vector_index_id=_optional_string(
                                getattr(result, "vector_index_id", None)
                            ),
                            title=_optional_string(getattr(result, "title", None)),
                            heading_path=tuple(
                                str(value)
                                for value in getattr(result, "heading_path", ())
                            ),
                            source_uri=_optional_string(
                                getattr(result, "source_uri", None)
                            ),
                            expanded_chunks=tuple(
                                _to_evaluation_expanded_chunk(chunk)
                                for chunk in getattr(result, "expanded_chunks", ())
                            ),
                            context_text=_optional_string(
                                getattr(result, "context_text", None)
                            ),
                            context_character_count=_optional_int(
                                getattr(result, "context_character_count", None)
                            ),
                            max_context_characters=_optional_int(
                                getattr(result, "max_context_characters", None)
                            ),
                            context_budget_exceeded=bool(
                                getattr(result, "context_budget_exceeded", False)
                            ),
                        )
                        for rank, result in enumerate(ranked, start=1)
                    ),
                    relevant_chunk_ids=tuple(sorted(relevant)),
                    first_relevant_rank=first_rank,
                    hit_at_k=float(first_rank is not None),
                    recall_at_k=retrieved_relevant / len(relevant),
                    reciprocal_rank=0.0 if first_rank is None else 1.0 / first_rank,
                    first_expanded_evidence_rank=first_expanded_rank,
                    expanded_evidence_hit_at_k=float(
                        first_expanded_rank is not None
                    ),
                    expanded_evidence_recall_at_k=(
                        len(expanded_retrieved & relevant) / len(relevant)
                    ),
                    expanded_evidence_reciprocal_rank=(
                        0.0
                        if first_expanded_rank is None
                        else 1.0 / first_expanded_rank
                    ),
                    expanded_chunk_count=len(expanded_chunks),
                    context_character_count=context_character_count,
                    unjudged_expanded_chunk_count=sum(
                        chunk.chunk_id not in relevant for chunk in expanded_chunks
                    ),
                    context_budget_exceeded_count=budget_exceeded_count,
                    latency_ms=latency_ms,
                )
            )
        count = len(query_results)
        approved_count = sum(
            item.review_status == "approved" for item in dataset.questions
        )
        latencies = sorted(item.latency_ms for item in query_results)
        context_lengths = sorted(
            item.context_character_count for item in query_results
        )
        expanded_chunk_count = sum(
            item.expanded_chunk_count for item in query_results
        )
        unjudged_expanded_chunk_count = sum(
            item.unjudged_expanded_chunk_count for item in query_results
        )
        return RetrievalEvaluationReport(
            evaluation_set_id=dataset.evaluation_set_id,
            evaluation_set_hash=dataset.content_hash,
            corpus_snapshot=dataset.corpus_snapshot,
            retriever=retriever_name,
            limit=limit,
            query_count=count,
            approved_query_count=approved_count,
            is_provisional=approved_count != count,
            hit_rate_at_k=sum(item.hit_at_k for item in query_results) / count,
            recall_at_k=sum(item.recall_at_k for item in query_results) / count,
            mrr=sum(item.reciprocal_rank for item in query_results) / count,
            expanded_evidence_hit_rate_at_k=sum(
                item.expanded_evidence_hit_at_k for item in query_results
            )
            / count,
            expanded_evidence_recall_at_k=sum(
                item.expanded_evidence_recall_at_k for item in query_results
            )
            / count,
            expanded_evidence_mrr=sum(
                item.expanded_evidence_reciprocal_rank for item in query_results
            )
            / count,
            mean_expanded_chunk_count=expanded_chunk_count / count,
            mean_context_characters=sum(context_lengths) / count,
            p95_context_characters=context_lengths[math.ceil(count * 0.95) - 1],
            unjudged_expansion_rate=(
                unjudged_expanded_chunk_count / expanded_chunk_count
                if expanded_chunk_count
                else 0.0
            ),
            context_budget_exceeded_count=sum(
                item.context_budget_exceeded_count for item in query_results
            ),
            mean_latency_ms=sum(latencies) / count,
            p95_latency_ms=latencies[math.ceil(count * 0.95) - 1],
            queries=tuple(query_results),
        )


def _load_query(payload: object) -> EvaluationQuery:
    if not isinstance(payload, dict):
        raise ValueError("Every evaluation question must be a JSON object")
    category = _required_string(payload, "category")
    if category not in EVALUATION_CATEGORIES:
        raise ValueError(f"Unsupported evaluation category: {category}")
    review_status = _required_string(payload, "review_status")
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"Unsupported review status: {review_status}")
    judgments_payload = payload.get("judgments")
    if not isinstance(judgments_payload, list) or not judgments_payload:
        raise ValueError("Every evaluation question needs at least one judgment")
    judgments = tuple(_load_judgment(item) for item in judgments_payload)
    keys = [(item.document_id, item.chunk_id) for item in judgments]
    if len(set(keys)) != len(keys):
        raise ValueError("Judgments within a question must be unique")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("Evaluation notes must be a string or null")
    return EvaluationQuery(
        query_id=_required_string(payload, "query_id"),
        query=_required_string(payload, "query"),
        category=category,
        review_status=review_status,
        judgments=judgments,
        notes=notes,
    )


def _load_judgment(payload: object) -> RelevanceJudgment:
    if not isinstance(payload, dict):
        raise ValueError("Every relevance judgment must be a JSON object")
    relevance = payload.get("relevance")
    if not isinstance(relevance, int) or relevance not in {1, 2, 3}:
        raise ValueError("Relevance must be an integer from 1 to 3")
    return RelevanceJudgment(
        document_id=_required_string(payload, "document_id"),
        chunk_id=_required_string(payload, "chunk_id"),
        relevance=relevance,
        evidence_quote=_required_string(payload, "evidence_quote"),
    )


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _to_evaluation_expanded_chunk(chunk: object) -> EvaluationExpandedChunk:
    return EvaluationExpandedChunk(
        chunk_id=str(getattr(chunk, "chunk_id")),
        document_id=str(getattr(chunk, "document_id")),
        ordinal=int(getattr(chunk, "ordinal")),
        relation=str(getattr(chunk, "relation")),
        distance=int(getattr(chunk, "distance")),
        heading_path=tuple(
            str(value) for value in getattr(chunk, "heading_path", ())
        ),
        page_start=_optional_int(getattr(chunk, "page_start", None)),
        page_end=_optional_int(getattr(chunk, "page_end", None)),
    )


def _fenced_markdown(text: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"