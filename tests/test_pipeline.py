import json
from pathlib import Path

from enterprise_rag_lab.cli import main
from enterprise_rag_lab.ingestion import SQLiteIngestionStore
from enterprise_rag_lab.pipeline import DirectoryPipelineService


def test_directory_pipeline_indexes_valid_files_and_isolates_failures(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "good.md").write_text(
        "# Good document\n\nA searchable batch processing example.",
        encoding="utf-8",
    )
    (root / "broken.pdf").write_bytes(b"not a PDF")
    (root / "notes.txt").write_text("ignored", encoding="utf-8")
    store = SQLiteIngestionStore(tmp_path / "state.sqlite3")
    service = DirectoryPipelineService(store)

    result = service.process(
        root,
        extensions=("md", "pdf"),
        source_uri_base="https://example.test/repository",
    )

    assert result.discovered_file_count == 2
    assert result.ignored_file_count == 1
    assert result.succeeded_file_count == 1
    assert result.failed_file_count == 1
    assert result.total_chunk_count == 1
    assert [Path(item.source_path).name for item in result.files] == ["broken.pdf", "good.md"]
    assert result.files[0].failed_stage == "ingestion"
    assert result.files[1].status == "succeeded"
    assert result.files[1].index_id

    documents = store.list_documents()
    assert len(documents) == 1
    assert documents[0]["source_uri"] == "https://example.test/repository/nested/good.md"
    assert documents[0]["index_status"] == "keyword_indexed"

    replayed = service.process(
        root,
        extensions=("md", "pdf"),
        source_uri_base="https://example.test/repository",
    )
    assert replayed.files[1].index_id == result.files[1].index_id
    assert len(store.list_documents()) == 1
    assert len(service.keyword.search("batch processing")) == 1


def test_process_directory_cli_prints_summary_without_success_details(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "one.md").write_text("# One\n\nKeyword indexing works.", encoding="utf-8")

    exit_code = main(
        [
            "--database",
            str(tmp_path / "state.sqlite3"),
            "process-directory",
            str(root),
            "--extension",
            "md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["succeeded_file_count"] == 1
    assert payload["failed_file_count"] == 0
    assert payload["total_chunk_count"] == 1
    assert payload["files"] == []


def test_directory_pipeline_reports_the_exact_failed_stage(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "one.md").write_text("# One\n\nValid source text.", encoding="utf-8")
    store = SQLiteIngestionStore(tmp_path / "state.sqlite3")

    result = DirectoryPipelineService(store).process(
        root,
        target_characters=1200,
        max_characters=800,
    )

    assert result.failed_file_count == 1
    assert result.files[0].failed_stage == "chunking"
    assert result.files[0].error_code == "pipeline_failed"
    assert "target_characters" in (result.files[0].error_message or "")