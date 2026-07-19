"""Run the deterministic document pipeline over a directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

from enterprise_rag_lab.chunking import (
    DEFAULT_MAX_CHARACTERS,
    DEFAULT_TARGET_CHARACTERS,
    ChunkingService,
)
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import IngestionStatus
from enterprise_rag_lab.retrieval import KeywordSearchService

SUPPORTED_EXTENSIONS = frozenset({".doc", ".docx", ".markdown", ".md", ".pdf"})


@dataclass(frozen=True)
class PipelineFileResult:
    source_path: str
    status: str
    run_id: str
    document_id: str | None = None
    cleaning_id: str | None = None
    chunking_id: str | None = None
    index_id: str | None = None
    chunk_count: int = 0
    failed_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class DirectoryPipelineResult:
    root_path: str
    recursive: bool
    discovered_file_count: int
    ignored_file_count: int
    succeeded_file_count: int
    failed_file_count: int
    total_chunk_count: int
    files: tuple[PipelineFileResult, ...]


def _normalize_extensions(extensions: Iterable[str] | None) -> frozenset[str]:
    if extensions is None:
        return SUPPORTED_EXTENSIONS
    normalized = frozenset(
        extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
        for extension in extensions
    )
    unsupported = normalized - SUPPORTED_EXTENSIONS
    if unsupported:
        values = ", ".join(sorted(unsupported))
        raise ValueError(f"Unsupported extensions requested: {values}")
    if not normalized:
        raise ValueError("At least one extension is required")
    return normalized


def _source_uri(base: str | None, root: Path, path: Path) -> str | None:
    if base is None:
        return None
    relative_path = path.relative_to(root).as_posix()
    return f"{base.rstrip('/')}/{quote(relative_path)}"


class DirectoryPipelineService:
    def __init__(self, store: SQLiteIngestionStore) -> None:
        self.ingestion = IngestionService(store)
        self.cleaning = CleaningService(store)
        self.chunking = ChunkingService(store)
        self.keyword = KeywordSearchService(store)

    def process(
        self,
        root: str | Path,
        *,
        extensions: Iterable[str] | None = None,
        recursive: bool = True,
        source_uri_base: str | None = None,
        target_characters: int = DEFAULT_TARGET_CHARACTERS,
        max_characters: int = DEFAULT_MAX_CHARACTERS,
    ) -> DirectoryPipelineResult:
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise ValueError(f"Directory does not exist: {root_path}")

        selected_extensions = _normalize_extensions(extensions)
        discovered_paths = [
            path
            for path in (root_path.rglob("*") if recursive else root_path.glob("*"))
            if path.is_file()
        ]
        paths = sorted(
            (path for path in discovered_paths if path.suffix.casefold() in selected_extensions),
            key=lambda path: path.relative_to(root_path).as_posix().casefold(),
        )
        results = tuple(
            self._process_file(
                path,
                _source_uri(source_uri_base, root_path, path),
                target_characters,
                max_characters,
            )
            for path in paths
        )
        return DirectoryPipelineResult(
            root_path=str(root_path),
            recursive=recursive,
            discovered_file_count=len(paths),
            ignored_file_count=len(discovered_paths) - len(paths),
            succeeded_file_count=sum(result.status == "succeeded" for result in results),
            failed_file_count=sum(result.status == "failed" for result in results),
            total_chunk_count=sum(result.chunk_count for result in results),
            files=results,
        )

    def _process_file(
        self,
        path: Path,
        source_uri: str | None,
        target_characters: int,
        max_characters: int,
    ) -> PipelineFileResult:
        run = self.ingestion.ingest(path, source_uri)
        if run.status is IngestionStatus.FAILED or run.document_id is None:
            return PipelineFileResult(
                source_path=str(path),
                status="failed",
                run_id=run.run_id,
                failed_stage="ingestion",
                error_code=run.error_code,
                error_message=run.error_message,
            )

        document_id = run.document_id
        stage = "cleaning"
        try:
            cleaning = self.cleaning.clean_document(document_id)
            if cleaning is None:
                raise RuntimeError("No parsed version is available")
            stage = "chunking"
            chunking = self.chunking.chunk_document(
                document_id,
                target_characters,
                max_characters,
            )
            if chunking is None:
                raise RuntimeError("No cleaning version is available")
            stage = "keyword_indexing"
            index = self.keyword.index_document(document_id)
            if index is None:
                raise RuntimeError("No chunking version is available")
        except Exception as error:
            return PipelineFileResult(
                source_path=str(path),
                status="failed",
                run_id=run.run_id,
                document_id=document_id,
                failed_stage=stage,
                error_code="pipeline_failed",
                error_message=str(error),
            )

        return PipelineFileResult(
            source_path=str(path),
            status="succeeded",
            run_id=run.run_id,
            document_id=document_id,
            cleaning_id=cleaning.cleaning_id,
            chunking_id=chunking.chunking_id,
            index_id=index.index_id,
            chunk_count=len(chunking.chunks),
        )