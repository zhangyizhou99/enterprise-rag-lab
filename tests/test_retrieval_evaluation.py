import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from enterprise_rag_lab.chunking import ChunkingService
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.cli import main
from enterprise_rag_lab.evaluation import (
    RetrievalEvaluationService,
    load_evaluation_set,
    render_review_markdown,
    validate_evaluation_set,
)
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.retrieval import KeywordSearchService

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FakeResult:
    chunk_id: str
    document_id: str
    score: float = 0.03
    rrf_score: float = 0.03
    keyword_rank: int = 2
    keyword_score: float = 8.5
    vector_rank: int = 3
    vector_score: float = 0.9
    vector_index_id: str = "vector_test"
    expanded_chunks: tuple[Any, ...] = ()
    context_text: str | None = None
    context_character_count: int | None = None
    max_context_characters: int | None = None
    context_budget_exceeded: bool = False


@dataclass(frozen=True)
class FakeExpandedChunk:
    chunk_id: str
    document_id: str
    ordinal: int
    relation: str
    distance: int
    heading_path: tuple[str, ...] = ()
    page_start: int | None = None
    page_end: int | None = None


class FakeRetriever:
    def search(self, query: str, limit: int):
        assert limit == 3
        if query == "first":
            return (
                FakeResult("noise", "doc_noise"),
                FakeResult("chunk_a", "doc_a"),
            )
        return ()


def _write_dataset(path: Path, questions: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "evaluation_set_id": "test_set",
                "schema_version": "1.0",
                "corpus_snapshot": "snapshot_test",
                "annotation_policy": "Test policy",
                "questions": questions,
            }
        ),
        encoding="utf-8",
    )


def test_retrieval_metrics_have_explicit_hit_recall_and_mrr_semantics(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "evaluation.json"
    _write_dataset(
        dataset_path,
        [
            {
                "query_id": "q1",
                "query": "first",
                "category": "concept",
                "review_status": "approved",
                "judgments": [
                    {
                        "document_id": "doc_a",
                        "chunk_id": "chunk_a",
                        "relevance": 3,
                        "evidence_quote": "answer a",
                    },
                    {
                        "document_id": "doc_b",
                        "chunk_id": "chunk_b",
                        "relevance": 2,
                        "evidence_quote": "answer b",
                    },
                ],
            },
            {
                "query_id": "q2",
                "query": "second",
                "category": "troubleshooting",
                "review_status": "needs_human_review",
                "judgments": [
                    {
                        "document_id": "doc_c",
                        "chunk_id": "chunk_c",
                        "relevance": 3,
                        "evidence_quote": "answer c",
                    }
                ],
            },
        ],
    )

    report = RetrievalEvaluationService().evaluate(
        load_evaluation_set(dataset_path),
        FakeRetriever(),
        "fake",
        limit=3,
    )

    assert report.query_count == 2
    assert report.approved_query_count == 1
    assert report.is_provisional is True
    assert report.hit_rate_at_k == pytest.approx(0.5)
    assert report.recall_at_k == pytest.approx(0.25)
    assert report.mrr == pytest.approx(0.25)
    assert report.queries[0].first_relevant_rank == 2
    assert report.queries[0].recall_at_k == pytest.approx(0.5)
    assert report.queries[0].candidates[1].chunk_id == "chunk_a"
    assert report.queries[0].candidates[1].rrf_score == 0.03
    assert report.queries[0].candidates[1].keyword_rank == 2
    assert report.queries[0].candidates[1].keyword_score == 8.5
    assert report.queries[0].candidates[1].vector_rank == 3
    assert report.queries[0].candidates[1].vector_score == 0.9
    assert report.queries[0].candidates[1].vector_index_id == "vector_test"
    assert report.expanded_evidence_hit_rate_at_k == report.hit_rate_at_k
    assert report.expanded_evidence_recall_at_k == report.recall_at_k
    assert report.expanded_evidence_mrr == report.mrr
    assert report.p95_latency_ms >= 0


def test_expanded_evidence_metrics_do_not_change_anchor_metrics(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "expanded-evaluation.json"
    _write_dataset(
        dataset_path,
        [
            {
                "query_id": "q1",
                "query": "expanded",
                "category": "concept",
                "review_status": "approved",
                "judgments": [
                    {
                        "document_id": "doc_relevant",
                        "chunk_id": "chunk_relevant",
                        "relevance": 3,
                        "evidence_quote": "answer",
                    }
                ],
            }
        ],
    )
    relevant = FakeExpandedChunk(
        "chunk_relevant", "doc_relevant", 2, "next", 1
    )
    unjudged = FakeExpandedChunk(
        "chunk_unjudged", "doc_anchor", 0, "previous", 1
    )

    class ExpandedRetriever:
        def search(self, query: str, limit: int):
            return (
                FakeResult(
                    "anchor",
                    "doc_anchor",
                    expanded_chunks=(unjudged, relevant),
                    context_text="unjudged\n\nanchor\n\nanswer",
                    context_character_count=27,
                    max_context_characters=100,
                ),
            )

    report = RetrievalEvaluationService().evaluate(
        load_evaluation_set(dataset_path),
        ExpandedRetriever(),
        "expanded",
        limit=5,
    )

    assert report.hit_rate_at_k == 0.0
    assert report.recall_at_k == 0.0
    assert report.mrr == 0.0
    assert report.expanded_evidence_hit_rate_at_k == 1.0
    assert report.expanded_evidence_recall_at_k == 1.0
    assert report.expanded_evidence_mrr == 1.0
    assert report.mean_expanded_chunk_count == 2.0
    assert report.mean_context_characters == 27.0
    assert report.p95_context_characters == 27
    assert report.unjudged_expansion_rate == 0.5
    assert report.queries[0].first_expanded_evidence_rank == 1
    assert len(report.queries[0].candidates[0].expanded_chunks) == 2


def test_evaluation_validation_rejects_stale_chunk_and_quote(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "evaluation.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None
    dataset_path = tmp_path / "evaluation.json"
    _write_dataset(
        dataset_path,
        [
            {
                "query_id": "q1",
                "query": "如何配置 CORS？",
                "category": "configuration",
                "review_status": "needs_human_review",
                "judgments": [
                    {
                        "document_id": document_id,
                        "chunk_id": chunking.chunks[0].chunk_id,
                        "relevance": 3,
                        "evidence_quote": "不存在的证据文本",
                    },
                    {
                        "document_id": document_id,
                        "chunk_id": "chunk_stale",
                        "relevance": 2,
                        "evidence_quote": "irrelevant",
                    },
                ],
            }
        ],
    )

    with pytest.raises(ValueError, match="evidence quote is absent") as error:
        validate_evaluation_set(load_evaluation_set(dataset_path), store)

    assert "chunk_stale is not a latest chunk" in str(error.value)


def test_review_markdown_shows_full_current_chunk_and_provenance(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "evaluation.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md",
        "https://example.test/cors.md",
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None
    assert KeywordSearchService(store).index_document(document_id) is not None
    chunk = chunking.chunks[0]
    evidence_quote = chunk.text[:20]
    dataset_path = tmp_path / "evaluation.json"
    _write_dataset(
        dataset_path,
        [
            {
                "query_id": "q1",
                "query": "如何配置 CORS？",
                "category": "configuration",
                "review_status": "needs_human_review",
                "judgments": [
                    {
                        "document_id": document_id,
                        "chunk_id": chunk.chunk_id,
                        "relevance": 3,
                        "evidence_quote": evidence_quote,
                    }
                ],
            }
        ],
    )
    dataset = load_evaluation_set(dataset_path)

    markdown = render_review_markdown(dataset, store, start=1, limit=1)

    assert "人工审核 1-1" in markdown
    assert "以下相关度是种子建议，不是人工结论" in markdown
    assert "如何配置 CORS？" in markdown
    assert "https://example.test/cors.md" in markdown
    assert chunk.chunk_id in markdown
    assert evidence_quote in markdown
    assert chunk.text in markdown
    assert "本阶段只评估“问题 → Chunk”的检索相关性，尚未生成答案" in markdown
    assert "- [ ] 完整 Chunk 含有足以支撑回答的事实" in markdown
    assert "无需自行查库" in markdown

    with pytest.raises(ValueError, match="is not approved"):
        validate_evaluation_set(dataset, store, require_approved=True)


def test_evaluation_cli_validates_and_writes_review_batch(
    tmp_path: Path,
    capsys,
) -> None:
    database = tmp_path / "evaluation.sqlite3"
    store = SQLiteIngestionStore(database)
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None
    chunk = chunking.chunks[0]
    dataset_path = tmp_path / "evaluation.json"
    _write_dataset(
        dataset_path,
        [
            {
                "query_id": "q1",
                "query": "如何配置 CORS？",
                "category": "configuration",
                "review_status": "needs_human_review",
                "judgments": [
                    {
                        "document_id": document_id,
                        "chunk_id": chunk.chunk_id,
                        "relevance": 3,
                        "evidence_quote": chunk.text[:20],
                    }
                ],
            }
        ],
    )
    output = tmp_path / "review.md"

    exit_code = main(
        [
            "--database",
            str(database),
            "validate-evaluation-set",
            str(dataset_path),
        ]
    )
    validation = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert validation["question_count"] == 1
    assert validation["needs_human_review_count"] == 1

    exit_code = main(
        [
            "--database",
            str(database),
            "prepare-evaluation-review",
            str(dataset_path),
            "--output",
            str(output),
        ]
    )
    review = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert review["question_count"] == 1
    assert review["approved_question_count"] == 0
    assert "如何配置 CORS？" in output.read_text(encoding="utf-8")

    exit_code = main(
        [
            "--database",
            str(database),
            "validate-evaluation-set",
            str(dataset_path),
            "--require-approved",
        ]
    )
    failure = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert failure["error"] == "evaluation_validation_failed"
    assert "q1: is not approved" in failure["message"]

    report_path = tmp_path / "bm25-report.json"
    exit_code = main(
        [
            "--database",
            str(database),
            "evaluate-retrieval",
            str(dataset_path),
            "--retriever",
            "bm25",
            "--limit",
            "5",
            "--output",
            str(report_path),
        ]
    )
    evaluation = json.loads(capsys.readouterr().out)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert evaluation["is_provisional"] is True
    assert evaluation["approved_query_count"] == 0
    assert report["retriever"] == "bm25_fts5_trigram_or_v0.2.0"
    assert report["queries"][0]["query_id"] == "q1"
    assert "candidates" in report["queries"][0]