"""Command-line entry point for local ingestion workflows."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from enterprise_rag_lab.chunking import (
    DEFAULT_MAX_CHARACTERS,
    DEFAULT_TARGET_CHARACTERS,
    ChunkingService,
)
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.evaluation import (
    RetrievalEvaluationService,
    load_evaluation_set,
    render_review_markdown,
    validate_evaluation_set,
)
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import IngestionStatus
from enterprise_rag_lab.pipeline import DirectoryPipelineService
from enterprise_rag_lab.retrieval import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_CONTEXT_CHARACTERS,
    DEFAULT_MODEL_REVISION,
    DEFAULT_NEIGHBOR_DEPTH,
    DEFAULT_QDRANT_PATH,
    DEFAULT_RRF_CANDIDATE_LIMIT,
    ContextExpansionService,
    EmbeddingService,
    KEYWORD_RETRIEVER_ID,
    KeywordSearchService,
    QdrantVectorBackend,
    RRF_K,
    RRFSearchService,
    SentenceTransformerEncoder,
    VectorIndexService,
    VectorSearchService,
)

DEFAULT_DATABASE = Path("data/state/ingestion.sqlite3")
DEFAULT_EVALUATION_SET = Path("data/evaluation/fastapi_retrieval_v1.json")


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _print_json(value: Any) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding is not None:
        try:
            content.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            content = json.dumps(
                value,
                ensure_ascii=True,
                indent=2,
                default=_json_default,
            )
    print(content)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enterprise-rag-lab")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Parse and persist one document")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--source-uri")

    process_directory = commands.add_parser(
        "process-directory",
        help="Ingest, clean, chunk, and index documents in a directory",
    )
    process_directory.add_argument("path", type=Path)
    process_directory.add_argument(
        "--extension",
        action="append",
        dest="extensions",
        help="Include one supported extension; repeat to include more",
    )
    process_directory.add_argument("--no-recursive", action="store_false", dest="recursive")
    process_directory.add_argument("--source-uri-base")
    process_directory.add_argument(
        "--target-characters",
        type=int,
        default=DEFAULT_TARGET_CHARACTERS,
    )
    process_directory.add_argument(
        "--max-characters",
        type=int,
        default=DEFAULT_MAX_CHARACTERS,
    )
    process_directory.add_argument(
        "--details",
        action="store_true",
        help="Include successful per-file results in the JSON output",
    )

    inspect_run = commands.add_parser("inspect-run", help="Inspect one ingestion run")
    inspect_run.add_argument("run_id")

    commands.add_parser("list-documents", help="List ingested documents")

    inspect_document = commands.add_parser(
        "inspect-document",
        help="Inspect document metadata and stored versions",
    )
    inspect_document.add_argument("document_id")

    list_blocks = commands.add_parser(
        "list-blocks",
        help="List source-addressable parsed blocks for a document",
    )
    list_blocks.add_argument("document_id")
    list_blocks.add_argument("--limit", type=int, default=20)
    list_blocks.add_argument("--offset", type=int, default=0)

    clean_document = commands.add_parser(
        "clean-document",
        help="Replay the current cleaning rule set for a document",
    )
    clean_document.add_argument("document_id")

    inspect_cleaning = commands.add_parser(
        "inspect-cleaning",
        help="Inspect cleaning statistics and rule hits",
    )
    inspect_cleaning.add_argument("document_id")

    list_cleaned_blocks = commands.add_parser(
        "list-cleaned-blocks",
        help="List cleaned blocks while retaining source locations",
    )
    list_cleaned_blocks.add_argument("document_id")
    list_cleaned_blocks.add_argument("--limit", type=int, default=20)
    list_cleaned_blocks.add_argument("--offset", type=int, default=0)

    chunk_document = commands.add_parser(
        "chunk-document",
        help="Create retrieval chunks from the latest cleaned blocks",
    )
    chunk_document.add_argument("document_id")
    chunk_document.add_argument(
        "--target-characters",
        type=int,
        default=DEFAULT_TARGET_CHARACTERS,
    )
    chunk_document.add_argument(
        "--max-characters",
        type=int,
        default=DEFAULT_MAX_CHARACTERS,
    )

    inspect_chunking = commands.add_parser(
        "inspect-chunking",
        help="Inspect the latest chunking version and size statistics",
    )
    inspect_chunking.add_argument("document_id")

    list_chunks = commands.add_parser(
        "list-chunks",
        help="List retrieval chunks with source and neighbor provenance",
    )
    list_chunks.add_argument("document_id")
    list_chunks.add_argument("--limit", type=int, default=20)
    list_chunks.add_argument("--offset", type=int, default=0)

    index_document = commands.add_parser(
        "index-document",
        help="Build the FTS5 keyword index for the latest chunks",
    )
    index_document.add_argument("document_id")

    inspect_index = commands.add_parser(
        "inspect-index",
        help="Inspect the latest keyword index version",
    )
    inspect_index.add_argument("document_id")

    embed_document = commands.add_parser(
        "embed-document",
        help="Generate and persist embeddings for the latest chunks",
    )
    embed_document.add_argument("document_id")
    embed_document.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    embed_document.add_argument("--revision", default=DEFAULT_MODEL_REVISION)
    embed_document.add_argument("--batch-size", type=int, default=32)
    embed_document.add_argument("--allow-truncation", action="store_true")

    embed_all = commands.add_parser(
        "embed-all",
        help="Generate embeddings for the latest chunks of every document",
    )
    embed_all.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    embed_all.add_argument("--revision", default=DEFAULT_MODEL_REVISION)
    embed_all.add_argument("--batch-size", type=int, default=32)
    embed_all.add_argument("--allow-truncation", action="store_true")

    inspect_embedding = commands.add_parser(
        "inspect-embedding",
        help="Inspect the latest embedding version without printing vectors",
    )
    inspect_embedding.add_argument("document_id")

    sync_vector_index = commands.add_parser(
        "sync-vector-index",
        help="Sync a versioned snapshot of the latest embeddings to Qdrant",
    )
    sync_vector_index.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    sync_vector_index.add_argument("--batch-size", type=int, default=128)

    commands.add_parser(
        "inspect-vector-index",
        help="Inspect the latest successfully synchronized vector snapshot",
    )

    vector_search = commands.add_parser(
        "vector-search",
        help="Search the latest Qdrant snapshot with cosine similarity",
    )
    vector_search.add_argument("query")
    vector_search.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    vector_search.add_argument("--limit", type=int, default=10)

    hybrid_search = commands.add_parser(
        "hybrid-search",
        help="Fuse BM25 and vector candidates with reciprocal-rank fusion",
    )
    hybrid_search.add_argument("query")
    hybrid_search.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    hybrid_search.add_argument("--limit", type=int, default=5)
    hybrid_search.add_argument(
        "--candidate-limit",
        type=int,
        default=DEFAULT_RRF_CANDIDATE_LIMIT,
    )
    hybrid_search.add_argument("--expand-context", action="store_true")
    hybrid_search.add_argument(
        "--neighbor-depth",
        type=int,
        default=DEFAULT_NEIGHBOR_DEPTH,
    )
    hybrid_search.add_argument(
        "--max-context-characters",
        type=int,
        default=DEFAULT_MAX_CONTEXT_CHARACTERS,
    )

    search = commands.add_parser(
        "search",
        help="Search the latest keyword indexes with BM25 ranking",
    )
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    validate_evaluation = commands.add_parser(
        "validate-evaluation-set",
        help="Validate evaluation judgments against the current corpus snapshot",
    )
    validate_evaluation.add_argument(
        "dataset",
        type=Path,
        nargs="?",
        default=DEFAULT_EVALUATION_SET,
    )
    validate_evaluation.add_argument("--require-approved", action="store_true")

    prepare_review = commands.add_parser(
        "prepare-evaluation-review",
        help="Write a human-readable review batch with complete source chunks",
    )
    prepare_review.add_argument(
        "dataset",
        type=Path,
        nargs="?",
        default=DEFAULT_EVALUATION_SET,
    )
    prepare_review.add_argument("--start", type=int, default=1)
    prepare_review.add_argument("--limit", type=int, default=5)
    prepare_review.add_argument("--output", type=Path)

    evaluate_retrieval = commands.add_parser(
        "evaluate-retrieval",
        help="Evaluate BM25, vector, or RRF Top-K and persist per-query candidates",
    )
    evaluate_retrieval.add_argument(
        "dataset",
        type=Path,
        nargs="?",
        default=DEFAULT_EVALUATION_SET,
    )
    evaluate_retrieval.add_argument(
        "--retriever",
        choices=("bm25", "vector", "rrf", "rrf-context"),
        required=True,
    )
    evaluate_retrieval.add_argument("--limit", type=int, default=5)
    evaluate_retrieval.add_argument(
        "--candidate-limit",
        type=int,
        default=DEFAULT_RRF_CANDIDATE_LIMIT,
        help="Per-source candidate depth used by RRF",
    )
    evaluate_retrieval.add_argument(
        "--neighbor-depth",
        type=int,
        default=DEFAULT_NEIGHBOR_DEPTH,
    )
    evaluate_retrieval.add_argument(
        "--max-context-characters",
        type=int,
        default=DEFAULT_MAX_CONTEXT_CHARACTERS,
    )
    evaluate_retrieval.add_argument("--output", type=Path)
    evaluate_retrieval.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    evaluate_retrieval.add_argument("--require-approved", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    store = SQLiteIngestionStore(arguments.database)

    if arguments.command == "ingest":
        run = IngestionService(store).ingest(arguments.path, arguments.source_uri)
        _print_json(asdict(run))
        return 0 if run.status is IngestionStatus.SUCCEEDED else 1

    if arguments.command == "process-directory":
        try:
            result = DirectoryPipelineService(store).process(
                arguments.path,
                extensions=arguments.extensions,
                recursive=arguments.recursive,
                source_uri_base=arguments.source_uri_base,
                target_characters=arguments.target_characters,
                max_characters=arguments.max_characters,
            )
        except ValueError as error:
            _print_json({"error": "invalid_directory_pipeline", "message": str(error)})
            return 2
        payload = asdict(result)
        if not arguments.details:
            payload["files"] = [
                asdict(file_result)
                for file_result in result.files
                if file_result.status == "failed"
            ]
        _print_json(payload)
        return 1 if result.failed_file_count else 0

    if arguments.command == "inspect-run":
        run = store.get_run(arguments.run_id)
        if run is None:
            _print_json({"error": "run_not_found", "run_id": arguments.run_id})
            return 2
        _print_json(asdict(run))
        return 0

    if arguments.command == "list-documents":
        _print_json(store.list_documents())
        return 0

    if arguments.command == "inspect-document":
        document = store.inspect_document(arguments.document_id)
        if document is None:
            _print_json({"error": "document_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(document)
        return 0

    if arguments.command == "clean-document":
        result = CleaningService(store).clean_document(arguments.document_id)
        if result is None:
            _print_json({"error": "document_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(
            {
                "cleaning_id": result.cleaning_id,
                "source_version_id": result.source_version_id,
                "cleaner_version": result.cleaner_version,
                "rule_set_version": result.rule_set_version,
                "stats": asdict(result.stats),
            }
        )
        return 0

    if arguments.command == "inspect-cleaning":
        result = store.inspect_cleaning(arguments.document_id)
        if result is None:
            _print_json({"error": "cleaning_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(result)
        return 0

    if arguments.command == "chunk-document":
        try:
            result = ChunkingService(store).chunk_document(
                arguments.document_id,
                arguments.target_characters,
                arguments.max_characters,
            )
        except ValueError as error:
            _print_json({"error": "invalid_chunk_sizes", "message": str(error)})
            return 2
        if result is None:
            _print_json({"error": "cleaning_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(
            {
                "chunking_id": result.chunking_id,
                "cleaning_id": result.cleaning_id,
                "document_id": result.document_id,
                "chunker_version": result.chunker_version,
                "target_characters": result.target_characters,
                "max_characters": result.max_characters,
                "chunk_count": len(result.chunks),
            }
        )
        return 0

    if arguments.command == "inspect-chunking":
        result = store.inspect_chunking(arguments.document_id)
        if result is None:
            _print_json({"error": "chunking_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(result)
        return 0

    if arguments.command == "index-document":
        result = KeywordSearchService(store).index_document(arguments.document_id)
        if result is None:
            _print_json({"error": "chunking_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(asdict(result))
        return 0

    if arguments.command == "inspect-index":
        result = store.inspect_keyword_index(arguments.document_id)
        if result is None:
            _print_json({"error": "index_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(result)
        return 0

    if arguments.command == "embed-document":
        try:
            encoder = SentenceTransformerEncoder(arguments.model, arguments.revision)
            result = EmbeddingService(store, encoder).embed_document(
                arguments.document_id,
                arguments.batch_size,
                arguments.allow_truncation,
            )
        except (RuntimeError, ValueError, OSError) as error:
            _print_json({"error": "embedding_failed", "message": str(error)})
            return 1
        if result is None:
            _print_json({"error": "chunking_not_found", "document_id": arguments.document_id})
            return 2
        _print_json(
            {
                "embedding_id": result.embedding_id,
                "chunking_id": result.chunking_id,
                "document_id": result.document_id,
                "embedder_version": result.embedder_version,
                "model_name": result.model_name,
                "model_revision": result.model_revision,
                "dimension": result.dimension,
                "normalized": result.normalized,
                "passage_prefix": result.passage_prefix,
                "max_sequence_length": result.max_sequence_length,
                "embedded_chunk_count": len(result.embeddings),
                "truncated_chunk_count": sum(
                    embedding.truncated for embedding in result.embeddings
                ),
            }
        )
        return 0

    if arguments.command == "embed-all":
        try:
            encoder = SentenceTransformerEncoder(arguments.model, arguments.revision)
        except (RuntimeError, ValueError, OSError) as error:
            _print_json({"error": "embedding_failed", "message": str(error)})
            return 1
        service = EmbeddingService(store, encoder)
        succeeded_document_count = 0
        embedded_chunk_count = 0
        truncated_chunk_count = 0
        failures: list[dict[str, str]] = []
        documents = store.list_documents()
        for document in documents:
            document_id = str(document["document_id"])
            try:
                result = service.embed_document(
                    document_id,
                    arguments.batch_size,
                    arguments.allow_truncation,
                )
            except (RuntimeError, ValueError, OSError) as error:
                failures.append({"document_id": document_id, "message": str(error)})
                continue
            if result is None:
                failures.append(
                    {"document_id": document_id, "message": "No chunking version is available"}
                )
                continue
            succeeded_document_count += 1
            embedded_chunk_count += len(result.embeddings)
            truncated_chunk_count += sum(
                embedding.truncated for embedding in result.embeddings
            )
        _print_json(
            {
                "document_count": len(documents),
                "succeeded_document_count": succeeded_document_count,
                "failed_document_count": len(failures),
                "embedded_chunk_count": embedded_chunk_count,
                "truncated_chunk_count": truncated_chunk_count,
                "model_name": encoder.model_name,
                "model_revision": encoder.model_revision,
                "dimension": encoder.dimension,
                "max_sequence_length": encoder.max_sequence_length,
                "failures": failures,
            }
        )
        return 1 if failures else 0

    if arguments.command == "inspect-embedding":
        result = store.inspect_embedding(arguments.document_id)
        if result is None:
            _print_json(
                {"error": "embedding_not_found", "document_id": arguments.document_id}
            )
            return 2
        _print_json(result)
        return 0

    if arguments.command == "sync-vector-index":
        try:
            with closing(QdrantVectorBackend(arguments.qdrant_path)) as backend:
                result = VectorIndexService(store, backend).sync_latest(
                    arguments.batch_size
                )
        except (RuntimeError, ValueError, OSError) as error:
            _print_json({"error": "vector_index_failed", "message": str(error)})
            return 1
        _print_json(
            {
                "vector_index_id": result.vector_index_id,
                "collection_name": result.collection_name,
                "indexer_version": result.indexer_version,
                "model_name": result.model_name,
                "model_revision": result.model_revision,
                "dimension": result.dimension,
                "distance": result.distance,
                "normalized": result.normalized,
                "query_prefix": result.query_prefix,
                "indexed_document_count": len(result.members),
                "indexed_chunk_count": sum(
                    member.indexed_chunk_count for member in result.members
                ),
            }
        )
        return 0

    if arguments.command == "inspect-vector-index":
        result = store.inspect_vector_index()
        if result is None:
            _print_json({"error": "vector_index_not_found"})
            return 2
        _print_json(result)
        return 0

    if arguments.command == "vector-search":
        index = store.inspect_vector_index()
        if index is None:
            _print_json({"error": "vector_index_not_found"})
            return 2
        try:
            encoder = SentenceTransformerEncoder(
                str(index["model_name"]),
                str(index["model_revision"]),
            )
            with closing(QdrantVectorBackend(arguments.qdrant_path)) as backend:
                results = VectorSearchService(store, backend, encoder).search(
                    arguments.query,
                    arguments.limit,
                )
        except (RuntimeError, ValueError, OSError) as error:
            _print_json({"error": "vector_search_failed", "message": str(error)})
            return 1
        _print_json(
            {
                "query": arguments.query,
                "vector_index_id": index["vector_index_id"],
                "collection_name": index["collection_name"],
                "model_name": index["model_name"],
                "model_revision": index["model_revision"],
                "distance": index["distance"],
                "results": [asdict(result) for result in results],
            }
        )
        return 0

    if arguments.command == "hybrid-search":
        index = store.inspect_vector_index()
        if index is None:
            _print_json({"error": "vector_index_not_found"})
            return 2
        try:
            encoder = SentenceTransformerEncoder(
                str(index["model_name"]),
                str(index["model_revision"]),
            )
            with closing(QdrantVectorBackend(arguments.qdrant_path)) as backend:
                hybrid_service = RRFSearchService(
                    KeywordSearchService(store),
                    VectorSearchService(store, backend, encoder),
                    arguments.candidate_limit,
                )
                service = (
                    ContextExpansionService(
                        store,
                        hybrid_service,
                        arguments.neighbor_depth,
                        arguments.max_context_characters,
                    )
                    if arguments.expand_context
                    else hybrid_service
                )
                results = service.search(arguments.query, arguments.limit)
        except (RuntimeError, ValueError, OSError) as error:
            _print_json({"error": "hybrid_search_failed", "message": str(error)})
            return 1
        _print_json(
            {
                "query": arguments.query,
                "retriever": service.retriever_id,
                "rrf_k": RRF_K,
                "candidate_limit": hybrid_service.candidate_limit,
                "context_expansion": arguments.expand_context,
                "neighbor_depth": (
                    arguments.neighbor_depth if arguments.expand_context else None
                ),
                "max_context_characters": (
                    arguments.max_context_characters
                    if arguments.expand_context
                    else None
                ),
                "vector_index_id": index["vector_index_id"],
                "results": [asdict(result) for result in results],
            }
        )
        return 0

    if arguments.command == "search":
        try:
            results = KeywordSearchService(store).search(arguments.query, arguments.limit)
        except ValueError as error:
            _print_json({"error": "invalid_search", "message": str(error)})
            return 2
        _print_json([asdict(result) for result in results])
        return 0

    if arguments.command == "validate-evaluation-set":
        try:
            dataset = load_evaluation_set(arguments.dataset)
            summary = validate_evaluation_set(
                dataset,
                store,
                require_approved=arguments.require_approved,
            )
        except (OSError, ValueError) as error:
            _print_json({"error": "evaluation_validation_failed", "message": str(error)})
            return 1
        _print_json(summary)
        return 0

    if arguments.command == "prepare-evaluation-review":
        try:
            dataset = load_evaluation_set(arguments.dataset)
            markdown = render_review_markdown(
                dataset,
                store,
                start=arguments.start,
                limit=arguments.limit,
            )
            end = min(arguments.start + arguments.limit - 1, len(dataset.questions))
            output = arguments.output or Path(
                "data/evaluation/reviews"
            ) / f"{dataset.evaluation_set_id}_{arguments.start:03d}-{end:03d}.md"
            _write_text(output, markdown)
        except (OSError, ValueError) as error:
            _print_json({"error": "evaluation_review_failed", "message": str(error)})
            return 1
        _print_json(
            {
                "evaluation_set_id": dataset.evaluation_set_id,
                "output": output,
                "start": arguments.start,
                "end": end,
                "question_count": end - arguments.start + 1,
                "approved_question_count": sum(
                    question.review_status == "approved"
                    for question in dataset.questions[arguments.start - 1 : end]
                ),
            }
        )
        return 0

    if arguments.command == "evaluate-retrieval":
        try:
            dataset = load_evaluation_set(arguments.dataset)
            validate_evaluation_set(
                dataset,
                store,
                require_approved=arguments.require_approved,
            )
            service = RetrievalEvaluationService()
            if arguments.retriever == "bm25":
                report = service.evaluate(
                    dataset,
                    KeywordSearchService(store),
                    KEYWORD_RETRIEVER_ID,
                    arguments.limit,
                )
            else:
                index = store.inspect_vector_index()
                if index is None:
                    raise ValueError("No vector index snapshot is available")
                encoder = SentenceTransformerEncoder(
                    str(index["model_name"]),
                    str(index["model_revision"]),
                )
                with closing(QdrantVectorBackend(arguments.qdrant_path)) as backend:
                    vector_retriever = VectorSearchService(store, backend, encoder)
                    if arguments.retriever == "vector":
                        retriever = vector_retriever
                        retriever_name = "qdrant_e5_cosine"
                    else:
                        hybrid_retriever = RRFSearchService(
                            KeywordSearchService(store),
                            vector_retriever,
                            arguments.candidate_limit,
                        )
                        if arguments.retriever == "rrf-context":
                            context_retriever = ContextExpansionService(
                                store,
                                hybrid_retriever,
                                arguments.neighbor_depth,
                                arguments.max_context_characters,
                            )
                            retriever = context_retriever
                            retriever_name = context_retriever.retriever_id
                        else:
                            retriever = hybrid_retriever
                            retriever_name = hybrid_retriever.retriever_id
                    report = service.evaluate(
                        dataset,
                        retriever,
                        retriever_name,
                        arguments.limit,
                    )
            output = arguments.output or Path(
                "data/evaluation/reports"
            ) / (
                f"{dataset.evaluation_set_id}_{arguments.retriever}_"
                f"top{arguments.limit}.json"
            )
            _write_text(
                output,
                json.dumps(
                    asdict(report),
                    ensure_ascii=False,
                    indent=2,
                    default=_json_default,
                )
                + "\n",
            )
        except (OSError, RuntimeError, ValueError) as error:
            _print_json({"error": "retrieval_evaluation_failed", "message": str(error)})
            return 1
        _print_json(
            {
                "evaluation_set_id": report.evaluation_set_id,
                "retriever": report.retriever,
                "output": output,
                "limit": report.limit,
                "query_count": report.query_count,
                "approved_query_count": report.approved_query_count,
                "is_provisional": report.is_provisional,
                "hit_rate_at_k": report.hit_rate_at_k,
                "recall_at_k": report.recall_at_k,
                "mrr": report.mrr,
                "expanded_evidence_hit_rate_at_k": (
                    report.expanded_evidence_hit_rate_at_k
                ),
                "expanded_evidence_recall_at_k": (
                    report.expanded_evidence_recall_at_k
                ),
                "expanded_evidence_mrr": report.expanded_evidence_mrr,
                "mean_expanded_chunk_count": report.mean_expanded_chunk_count,
                "mean_context_characters": report.mean_context_characters,
                "p95_context_characters": report.p95_context_characters,
                "unjudged_expansion_rate": report.unjudged_expansion_rate,
                "context_budget_exceeded_count": (
                    report.context_budget_exceeded_count
                ),
                "mean_latency_ms": report.mean_latency_ms,
                "p95_latency_ms": report.p95_latency_ms,
            }
        )
        return 0

    if arguments.limit < 1 or arguments.limit > 200 or arguments.offset < 0:
        _print_json({"error": "invalid_pagination", "limit": arguments.limit, "offset": arguments.offset})
        return 2
    if arguments.command == "list-blocks":
        blocks = store.list_blocks(arguments.document_id, arguments.limit, arguments.offset)
    elif arguments.command == "list-cleaned-blocks":
        blocks = store.list_cleaned_blocks(
            arguments.document_id,
            arguments.limit,
            arguments.offset,
        )
    else:
        blocks = store.list_chunks(
            arguments.document_id,
            arguments.limit,
            arguments.offset,
        )
    _print_json(blocks)
    return 0