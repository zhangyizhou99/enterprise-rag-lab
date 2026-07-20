"""FastAPI adapter over the existing ingestion and retrieval services."""

from __future__ import annotations

import json
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from enterprise_rag_lab.chunking import ChunkingService
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import ContextExpansionResult, IngestionStatus
from enterprise_rag_lab.retrieval import (
    DEFAULT_MAX_CONTEXT_CHARACTERS,
    DEFAULT_NEIGHBOR_DEPTH,
    DEFAULT_QDRANT_PATH as RETRIEVAL_DEFAULT_QDRANT_PATH,
    DEFAULT_RRF_CANDIDATE_LIMIT,
    ContextExpansionService,
    KeywordSearchService,
    QdrantVectorBackend,
    RRFSearchService,
    SentenceTransformerEncoder,
    VectorSearchService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"
DEFAULT_DATABASE = PROJECT_ROOT / "data/state/ingestion.sqlite3"
DEFAULT_QDRANT_PATH = PROJECT_ROOT / RETRIEVAL_DEFAULT_QDRANT_PATH
DEFAULT_REPORTS_DIRECTORY = PROJECT_ROOT / "data/evaluation/reports"
SUPPORTED_UPLOAD_EXTENSIONS = frozenset({".docx", ".markdown", ".md", ".pdf"})
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    mode: Literal["keyword", "hybrid"] = "keyword"
    limit: int = Field(default=5, ge=1, le=10)
    expand_context: bool = False


class DemoUnavailableError(RuntimeError):
    pass


class DemoService:
    def __init__(
        self,
        database: Path,
        qdrant_path: Path,
        reports_directory: Path,
    ) -> None:
        self.store = SQLiteIngestionStore(database)
        self.qdrant_path = qdrant_path
        self.reports_directory = reports_directory
        self._vector_lock = threading.Lock()
        self._vector_contract: tuple[object, ...] | None = None
        self._vector_backend: QdrantVectorBackend | None = None
        self._query_encoder: SentenceTransformerEncoder | None = None

    def close(self) -> None:
        with self._vector_lock:
            if self._vector_backend is not None:
                self._vector_backend.close()
                self._vector_backend = None

    def overview(self) -> dict[str, object]:
        documents = self.store.list_documents()
        chunk_count = 0
        for document in documents:
            source = self.store.get_latest_chunks(str(document["document_id"]))
            if source is not None:
                chunk_count += len(source[1])
        vector_index = self.store.inspect_vector_index()
        vector_ready = vector_index is not None and self.qdrant_path.exists()
        recent_documents = [
            {
                "document_id": document["document_id"],
                "title": document["title"],
                "source_format": document["source_format"],
                "index_status": document["index_status"],
                "source_uri": document["source_uri"],
                "updated_at": document["updated_at"],
            }
            for document in reversed(documents[-8:])
        ]
        return {
            "corpus": {
                "document_count": len(documents),
                "chunk_count": chunk_count,
                "keyword_indexed_document_count": sum(
                    document["index_status"] == "keyword_indexed"
                    for document in documents
                ),
            },
            "capabilities": {
                "keyword": any(
                    document["index_status"] == "keyword_indexed"
                    for document in documents
                ),
                "hybrid": vector_ready,
                "context_expansion": vector_ready,
                "answer_generation": False,
            },
            "vector_index": self._vector_summary(vector_index, vector_ready),
            "evaluation_reports": self._load_evaluation_reports(),
            "recent_documents": recent_documents,
        }

    def search(self, request: SearchRequest) -> dict[str, object]:
        started_at = time.perf_counter()
        query = " ".join(request.query.split())
        if request.mode == "keyword":
            results = KeywordSearchService(self.store).search(query, request.limit)
            retriever = "bm25_fts5_trigram_or"
            serialized = [asdict(result) for result in results]
            vector_index_id = None
        else:
            serialized, retriever, vector_index_id = self._hybrid_search(
                query,
                request.limit,
                request.expand_context,
            )
        return {
            "query": query,
            "mode": request.mode,
            "retriever": retriever,
            "context_expansion": request.expand_context and request.mode == "hybrid",
            "vector_index_id": vector_index_id,
            "latency_ms": (time.perf_counter() - started_at) * 1000,
            "result_count": len(serialized),
            "results": serialized,
        }

    def ingest_uploaded(self, path: Path, source_uri: str | None) -> dict[str, object]:
        run = IngestionService(self.store).ingest(path, source_uri)
        if run.status is not IngestionStatus.SUCCEEDED or run.document_id is None:
            raise ValueError(run.error_message or "Document ingestion failed")
        document_id = run.document_id
        cleaning = CleaningService(self.store).clean_document(document_id)
        if cleaning is None:
            raise RuntimeError("No parsed version is available after ingestion")
        chunking = ChunkingService(self.store).chunk_document(document_id)
        if chunking is None:
            raise RuntimeError("No cleaning version is available after cleaning")
        keyword_index = KeywordSearchService(self.store).index_document(document_id)
        if keyword_index is None:
            raise RuntimeError("No chunking version is available for keyword indexing")
        parsed_blocks = self.store.list_blocks(document_id, limit=10_000)
        tables = [
            {
                "page_number": block["page_number"],
                "heading_path": block["heading_path"],
                "metadata": block["metadata"],
            }
            for block in parsed_blocks
            if block["block_type"] == "table"
        ]
        return {
            "status": "succeeded",
            "run_id": run.run_id,
            "document_id": document_id,
            "cleaning_id": cleaning.cleaning_id,
            "chunking_id": chunking.chunking_id,
            "index_id": keyword_index.index_id,
            "source_block_count": cleaning.stats.source_block_count,
            "cleaned_block_count": cleaning.stats.cleaned_block_count,
            "modified_block_count": cleaning.stats.modified_block_count,
            "removed_block_count": cleaning.stats.removed_block_count,
            "chunk_count": len(chunking.chunks),
            "table_count": len(tables),
            "tables": tables,
        }

    def _hybrid_search(
        self,
        query: str,
        limit: int,
        expand_context: bool,
    ) -> tuple[list[dict[str, Any]], str, object]:
        index = self.store.inspect_vector_index()
        if index is None:
            raise DemoUnavailableError("No vector index snapshot is available")
        if not self.qdrant_path.exists():
            raise DemoUnavailableError("The local Qdrant snapshot is unavailable")
        with self._vector_lock:
            self._ensure_vector_resources(index)
            assert self._vector_backend is not None
            assert self._query_encoder is not None
            hybrid = RRFSearchService(
                KeywordSearchService(self.store),
                VectorSearchService(
                    self.store,
                    self._vector_backend,
                    self._query_encoder,
                ),
                DEFAULT_RRF_CANDIDATE_LIMIT,
            )
            retriever: RRFSearchService | ContextExpansionService = hybrid
            if expand_context:
                retriever = ContextExpansionService(
                    self.store,
                    hybrid,
                    DEFAULT_NEIGHBOR_DEPTH,
                    DEFAULT_MAX_CONTEXT_CHARACTERS,
                )
            results = retriever.search(query, limit)
            serialized = [self._serialize_hybrid_result(result) for result in results]
        return serialized, retriever.retriever_id, index["vector_index_id"]

    def _ensure_vector_resources(self, index: dict[str, object]) -> None:
        contract = (
            index["model_name"],
            index["model_revision"],
            index["vector_index_id"],
        )
        if contract == self._vector_contract:
            return
        if self._vector_backend is not None:
            self._vector_backend.close()
        self._query_encoder = SentenceTransformerEncoder(
            str(index["model_name"]),
            str(index["model_revision"]),
        )
        self._vector_backend = QdrantVectorBackend(self.qdrant_path)
        self._vector_contract = contract

    @staticmethod
    def _serialize_hybrid_result(result: object) -> dict[str, Any]:
        if isinstance(result, ContextExpansionResult):
            return {
                **asdict(result.anchor),
                "expanded_chunks": [asdict(chunk) for chunk in result.expanded_chunks],
                "context_text": result.context_text,
                "context_character_count": result.context_character_count,
                "max_context_characters": result.max_context_characters,
                "context_budget_exceeded": result.context_budget_exceeded,
            }
        return asdict(result)

    def _load_evaluation_reports(self) -> list[dict[str, object]]:
        reports: list[dict[str, object]] = []
        for path in self.reports_directory.glob("*_top5.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            retriever = str(payload.get("retriever", ""))
            if "context_" in retriever:
                report_id, label, order = "rrf-context", "RRF + Context", 4
            elif retriever.startswith("rrf_"):
                report_id, label, order = "rrf", "RRF Fusion", 3
            elif retriever.startswith("qdrant_"):
                report_id, label, order = "vector", "E5 / Qdrant", 2
            elif retriever.startswith("bm25_"):
                report_id, label, order = "keyword", "BM25 / FTS5", 1
            else:
                continue
            reports.append(
                {
                    "id": report_id,
                    "label": label,
                    "order": order,
                    "query_count": payload.get("query_count"),
                    "is_provisional": payload.get("is_provisional"),
                    "hit_rate_at_k": payload.get("hit_rate_at_k"),
                    "recall_at_k": payload.get("recall_at_k"),
                    "mrr": payload.get("mrr"),
                    "expanded_evidence_recall_at_k": payload.get(
                        "expanded_evidence_recall_at_k"
                    ),
                    "expanded_evidence_mrr": payload.get("expanded_evidence_mrr"),
                    "mean_latency_ms": payload.get("mean_latency_ms"),
                    "p95_latency_ms": payload.get("p95_latency_ms"),
                }
            )
        return sorted(reports, key=lambda report: int(report["order"]))

    @staticmethod
    def _vector_summary(
        index: dict[str, object] | None,
        ready: bool,
    ) -> dict[str, object] | None:
        if index is None:
            return None
        return {
            "ready": ready,
            "vector_index_id": index["vector_index_id"],
            "model_name": index["model_name"],
            "dimension": index["dimension"],
            "indexed_document_count": index["stored_member_count"],
            "indexed_chunk_count": index["indexed_chunk_count"],
        }


def create_app(
    *,
    database: str | Path = DEFAULT_DATABASE,
    qdrant_path: str | Path = DEFAULT_QDRANT_PATH,
    reports_directory: str | Path = DEFAULT_REPORTS_DIRECTORY,
    upload_directory: str | Path | None = None,
) -> FastAPI:
    database_path = Path(database)
    uploads = Path(upload_directory or database_path.parent / "uploads")
    service = DemoService(
        database_path,
        Path(qdrant_path),
        Path(reports_directory),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        service.close()

    app = FastAPI(
        title="Enterprise RAG Lab Demo",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.demo_service = service

    @app.get("/api/overview")
    def overview() -> dict[str, object]:
        return service.overview()

    @app.post("/api/search")
    def search(request: SearchRequest) -> dict[str, object]:
        try:
            return service.search(request)
        except DemoUnavailableError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "retriever_unavailable", "message": str(error)},
            ) from error
        except (RuntimeError, ValueError, OSError) as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "search_failed", "message": str(error)},
            ) from error

    @app.post("/api/documents")
    async def upload_document(
        file: Annotated[UploadFile, File()],
        source_uri: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.casefold()
        if not filename or suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail={
                    "code": "unsupported_document",
                    "message": "Upload a Markdown, DOCX, or PDF document",
                },
            )
        uploads.mkdir(parents=True, exist_ok=True)
        destination = uploads / filename
        temporary = uploads / f".{filename}.{uuid4().hex}.uploading"
        size = 0
        try:
            with temporary.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "code": "document_too_large",
                                "message": "Documents are limited to 25 MB",
                            },
                        )
                    output.write(chunk)
            temporary.replace(destination)
            try:
                return await run_in_threadpool(
                    service.ingest_uploaded,
                    destination,
                    source_uri,
                )
            except (RuntimeError, ValueError, OSError) as error:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "ingestion_failed", "message": str(error)},
                ) from error
        finally:
            await file.close()
            temporary.unlink(missing_ok=True)

    @app.get("/", include_in_schema=False)
    def index_page() -> FileResponse:
        return FileResponse(STATIC_DIRECTORY / "index.html")

    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_DIRECTORY),
        name="demo-assets",
    )
    return app