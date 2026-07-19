from pathlib import Path

from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import IngestionStatus, SourceFormat

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_successful_ingestion_persists_document_version_and_blocks(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "ingestion.sqlite3")
    service = IngestionService(store)
    source = PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"

    run = service.ingest(
        source,
        source_uri="https://github.com/fastapi/fastapi/blob/main/docs/zh/docs/tutorial/cors.md",
    )

    assert run.status is IngestionStatus.SUCCEEDED
    persisted_run = store.get_run(run.run_id)
    assert persisted_run == run
    document = store.get_document(run.document_id or "")
    assert document is not None
    assert document.source_format is SourceFormat.MARKDOWN
    assert document.source_uri and document.source_uri.startswith("https://github.com/")
    documents = store.list_documents()
    assert [item["document_id"] for item in documents] == [run.document_id]
    inspected = store.inspect_document(run.document_id or "")
    assert inspected is not None
    assert inspected["versions"][0]["block_count"] > 0
    blocks = store.list_blocks(run.document_id or "", limit=4)
    assert blocks[0]["heading_path"] == ["CORS（跨域资源共享）"]
    assert "heading_path_json" not in blocks[0]


def test_repeated_ingestion_is_idempotent(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "ingestion.sqlite3")
    service = IngestionService(store)
    source = PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"

    first_run = service.ingest(source)
    second_run = service.ingest(source)

    assert first_run.status is IngestionStatus.SUCCEEDED
    assert second_run.status is IngestionStatus.SUCCEEDED
    assert first_run.document_id == second_run.document_id


def test_failed_legacy_doc_ingestion_is_auditable(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "ingestion.sqlite3")
    service = IngestionService(store)
    source = tmp_path / "legacy-document.doc"
    source.write_bytes(b"legacy DOC routing fixture")

    run = service.ingest(source)

    assert run.status is IngestionStatus.FAILED
    assert run.error_code == "legacy_doc_conversion_required"
    persisted_run = store.get_run(run.run_id)
    assert persisted_run == run
    assert persisted_run and "LibreOffice" in (persisted_run.error_message or "")