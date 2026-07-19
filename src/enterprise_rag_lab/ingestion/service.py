"""Orchestrate parsing and persist auditable ingestion outcomes."""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import (
    Document,
    DocumentVersion,
    IngestionRun,
    IngestionStatus,
    SourceFormat,
)
from enterprise_rag_lab.parsers import DocumentParseError, parse_document

PARSER_VERSION = "0.3.0"
_CONTENT_TYPES = {
    SourceFormat.MARKDOWN: "text/markdown",
    SourceFormat.PDF: "application/pdf",
    SourceFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    SourceFormat.DOC: "application/msword",
}


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, value: str, length: int = 24) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


class IngestionService:
    def __init__(self, store: SQLiteIngestionStore) -> None:
        self.store = store

    def ingest(self, path: str | Path, source_uri: str | None = None) -> IngestionRun:
        source_path = Path(path).resolve()
        run = IngestionRun(
            run_id=f"run_{uuid.uuid4().hex}",
            source_path=str(source_path),
            status=IngestionStatus.PENDING,
        )
        self.store.start_run(run)
        started_at = time.perf_counter()

        try:
            content_hash = hash_file(source_path)
            result = parse_document(source_path)
            document_id = _stable_id("doc", str(source_path).casefold())
            canonical_value = source_uri or f"sha256:{content_hash}"
            document = Document(
                document_id=document_id,
                canonical_id=_stable_id("canonical", canonical_value),
                title=result.title,
                source_format=result.source_format,
                content_type=_CONTENT_TYPES[result.source_format],
                source_path=str(source_path),
                source_uri=source_uri,
                content_hash=content_hash,
            )
            version = DocumentVersion(
                version_id=_stable_id(
                    "version",
                    f"{document_id}:{content_hash}:{PARSER_VERSION}",
                ),
                document_id=document_id,
                content_hash=content_hash,
                parser_version=PARSER_VERSION,
                extracted_text=result.text,
                warnings=result.warnings,
            )
            completed_run = IngestionRun(
                run_id=run.run_id,
                source_path=run.source_path,
                status=IngestionStatus.SUCCEEDED,
                document_id=document_id,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
            )
            self.store.save_success(completed_run, document, version, result)
            return completed_run
        except Exception as error:
            error_code = error.code if isinstance(error, DocumentParseError) else "ingestion_failed"
            failed_run = IngestionRun(
                run_id=run.run_id,
                source_path=run.source_path,
                status=IngestionStatus.FAILED,
                error_code=error_code,
                error_message=str(error),
                duration_ms=int((time.perf_counter() - started_at) * 1000),
            )
            self.store.save_failure(failed_run)
            return failed_run