from pathlib import Path

from enterprise_rag_lab.chunking import ChunkingService
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import IngestionStatus
from enterprise_rag_lab.retrieval import KeywordSearchService

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _prepare_document(store: SQLiteIngestionStore, source: Path) -> str:
    run = IngestionService(store).ingest(source)
    assert run.status is IngestionStatus.SUCCEEDED
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    assert ChunkingService(store).chunk_document(document_id) is not None
    return document_id


def test_keyword_index_replays_and_searches_chinese_chunks(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "retrieval.sqlite3")
    document_id = _prepare_document(
        store,
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md",
    )
    service = KeywordSearchService(store)

    first = service.index_document(document_id)
    second = service.index_document(document_id)
    results = service.search("跨域资源共享", limit=5)

    assert first is not None
    assert second == first
    assert first.indexed_chunk_count > 0
    assert results
    assert results[0].document_id == document_id
    assert any(
        "跨域资源共享" in value
        for value in (results[0].text, *results[0].heading_path)
    )
    assert results[0].score > 0
    assert store.get_document(document_id).index_status == "keyword_indexed"  # type: ignore[union-attr]


def test_keyword_search_matches_paraphrased_natural_question(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "retrieval.sqlite3")
    document_id = _prepare_document(
        store,
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md",
    )
    service = KeywordSearchService(store)
    assert service.index_document(document_id) is not None

    results = service.search(
        '如何在 FastAPI 中配置允许跨域访问的源、方法和“请求头”？',
        limit=5,
    )

    assert results
    assert any(
        result.document_id == document_id and "CORSMiddleware" in result.text
        for result in results
    )


def test_keyword_search_returns_english_pdf_page_provenance(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "retrieval.sqlite3")
    document_id = _prepare_document(store, PROJECT_ROOT / "data/raw/pdf/rfc-9112.pdf")
    service = KeywordSearchService(store)
    assert service.index_document(document_id) is not None

    results = service.search("message parsing", limit=5)

    assert results
    assert results[0].document_id == document_id
    assert results[0].page_start is not None
    assert results[0].page_start == results[0].page_end
    assert "[" in results[0].snippet