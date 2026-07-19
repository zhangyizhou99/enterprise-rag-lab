import json
from pathlib import Path
from typing import Sequence

import pytest

from enterprise_rag_lab.chunking import ChunkingService
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.cli import main
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import (
    ChunkEmbedding,
    EmbeddingResult,
    VectorIndexMember,
    VectorIndexResult,
)
from enterprise_rag_lab.retrieval import (
    EncodedBatch,
    EmbeddingService,
    VectorIndexService,
    VectorMatch,
    VectorPoint,
    VectorSearchService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeVectorEncoder:
    model_name = "test/e5"
    model_revision = "commit-1"
    dimension = 3
    normalized = True
    passage_prefix = "passage: "
    query_prefix = "query: "
    max_sequence_length = 512

    def __init__(self) -> None:
        self.queries: list[str] = []

    def encode_passages(self, texts, batch_size: int) -> EncodedBatch:
        assert batch_size == 2
        return EncodedBatch(
            vectors=tuple(
                (1.0, 0.0, 0.0) if ordinal == 0 else (0.0, 1.0, 0.0)
                for ordinal, _ in enumerate(texts)
            ),
            token_counts=tuple(20 for _ in texts),
        )

    def encode_queries(self, texts, batch_size: int) -> EncodedBatch:
        assert batch_size == 1
        self.queries.extend(texts)
        return EncodedBatch(
            vectors=tuple((1.0, 0.0, 0.0) for _ in texts),
            token_counts=tuple(8 for _ in texts),
        )


class FakeVectorBackend:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, object]] = {}

    def ensure_collection(self, name: str, dimension: int, distance: str) -> None:
        configuration = self.collections.setdefault(
            name,
            {"dimension": dimension, "distance": distance, "points": {}},
        )
        assert configuration["dimension"] == dimension
        assert configuration["distance"] == distance

    def upsert(self, name: str, points: Sequence[VectorPoint]) -> None:
        stored = self.collections[name]["points"]
        assert isinstance(stored, dict)
        stored.update({point.point_id: point for point in points})

    def count(self, name: str) -> int:
        points = self.collections[name]["points"]
        assert isinstance(points, dict)
        return len(points)

    def search(
        self,
        name: str,
        vector: Sequence[float],
        limit: int,
    ) -> tuple[VectorMatch, ...]:
        points = self.collections[name]["points"]
        assert isinstance(points, dict)
        ranked = sorted(
            points.values(),
            key=lambda point: sum(
                left * right for left, right in zip(point.vector, vector, strict=True)
            ),
            reverse=True,
        )[:limit]
        return tuple(
            VectorMatch(
                score=sum(
                    left * right
                    for left, right in zip(point.vector, vector, strict=True)
                ),
                payload=point.payload,
            )
            for point in ranked
        )

    def close(self) -> None:
        pass


def test_vector_index_store_replays_auditable_snapshot(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "vector.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None
    embedding = EmbeddingResult(
        embedding_id="embedding_vector_test",
        chunking_id=chunking.chunking_id,
        document_id=document_id,
        embedder_version="test",
        model_name="test/e5",
        model_revision="commit-1",
        dimension=3,
        normalized=True,
        passage_prefix="passage: ",
        max_sequence_length=512,
        embeddings=tuple(
            ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                ordinal=chunk.ordinal,
                vector=(1.0, 0.0, 0.0),
                token_count=20,
                truncated=False,
            )
            for chunk in chunking.chunks
        ),
    )
    store.save_embeddings(embedding)
    result = VectorIndexResult(
        vector_index_id="vector_test",
        collection_name="enterprise_rag_test",
        indexer_version="test",
        model_name=embedding.model_name,
        model_revision=embedding.model_revision,
        dimension=embedding.dimension,
        distance="cosine",
        normalized=True,
        passage_prefix=embedding.passage_prefix,
        query_prefix="query: ",
        max_sequence_length=embedding.max_sequence_length,
        members=(
            VectorIndexMember(
                document_id=document_id,
                chunking_id=chunking.chunking_id,
                embedding_id=embedding.embedding_id,
                indexed_chunk_count=len(embedding.embeddings),
            ),
        ),
    )

    store.save_vector_index(result)
    store.save_vector_index(result)

    summary = store.inspect_vector_index()
    assert summary is not None
    assert summary["vector_index_id"] == result.vector_index_id
    assert summary["collection_name"] == result.collection_name
    assert summary["indexed_document_count"] == 1
    assert summary["stored_member_count"] == 1
    assert summary["indexed_chunk_count"] == len(embedding.embeddings)
    assert summary["normalized"] is True


def test_vector_index_syncs_latest_embeddings_and_searches_top_k(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "vector.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None
    encoder = FakeVectorEncoder()
    embedding = EmbeddingService(store, encoder).embed_document(document_id, batch_size=2)
    assert embedding is not None
    backend = FakeVectorBackend()
    service = VectorIndexService(store, backend)

    first = service.sync_latest(batch_size=3)
    second = service.sync_latest(batch_size=3)

    assert second == first
    assert first.vector_index_id.startswith("vector_")
    assert first.collection_name.startswith("enterprise_rag_")
    assert len(first.members) == 1
    assert backend.count(first.collection_name) == len(chunking.chunks)
    summary = store.inspect_vector_index()
    assert summary is not None
    assert summary["indexed_chunk_count"] == len(chunking.chunks)

    results = VectorSearchService(store, backend, encoder).search(
        "如何配置跨域资源共享？",
        limit=3,
    )

    assert encoder.queries == ["如何配置跨域资源共享？"]
    assert len(results) == 3
    assert results[0].chunk_id == chunking.chunks[0].chunk_id
    assert results[0].document_id == document_id
    assert results[0].score == 1.0
    assert results[0].vector_index_id == first.vector_index_id
    assert results[0].source_uri is None


def test_vector_index_rejects_stale_embeddings(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "vector.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    assert ChunkingService(store).chunk_document(document_id) is not None

    with pytest.raises(ValueError, match="missing matching embeddings"):
        VectorIndexService(store, FakeVectorBackend()).sync_latest()


def test_vector_cli_syncs_inspects_and_searches(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    database = tmp_path / "vector.sqlite3"
    store = SQLiteIngestionStore(database)
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    assert ChunkingService(store).chunk_document(document_id) is not None
    encoder = FakeVectorEncoder()
    assert EmbeddingService(store, encoder).embed_document(document_id, batch_size=2)
    backend = FakeVectorBackend()
    monkeypatch.setattr(
        "enterprise_rag_lab.cli.QdrantVectorBackend",
        lambda _path: backend,
    )
    monkeypatch.setattr(
        "enterprise_rag_lab.cli.SentenceTransformerEncoder",
        lambda *_args: encoder,
    )

    exit_code = main(
        [
            "--database",
            str(database),
            "sync-vector-index",
            "--qdrant-path",
            str(tmp_path / "qdrant"),
            "--batch-size",
            "3",
        ]
    )
    sync_payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert sync_payload["indexed_document_count"] == 1
    assert sync_payload["indexed_chunk_count"] > 0
    assert "members" not in sync_payload

    exit_code = main(["--database", str(database), "inspect-vector-index"])
    inspect_payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert inspect_payload["vector_index_id"] == sync_payload["vector_index_id"]

    exit_code = main(
        [
            "--database",
            str(database),
            "vector-search",
            "如何配置跨域资源共享？",
            "--qdrant-path",
            str(tmp_path / "qdrant"),
            "--limit",
            "2",
        ]
    )
    search_payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert search_payload["distance"] == "cosine"
    assert len(search_payload["results"]) == 2
    assert search_payload["results"][0]["rank"] == 1
    assert "vector" not in search_payload["results"][0]