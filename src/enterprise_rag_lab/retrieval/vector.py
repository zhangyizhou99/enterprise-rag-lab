"""Versioned Qdrant vector snapshots and cosine Top-K retrieval."""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import (
    VectorIndexMember,
    VectorIndexResult,
    VectorSearchResult,
)
from enterprise_rag_lab.retrieval.embedding import (
    DEFAULT_QUERY_PREFIX,
    EncodedBatch,
    QueryEmbeddingEncoder,
)

VECTOR_INDEXER_VERSION = "0.1.0"
VECTOR_DISTANCE = "cosine"
DEFAULT_QDRANT_PATH = Path("data/state/qdrant")


@dataclass(frozen=True, slots=True)
class VectorPoint:
    point_id: str
    vector: tuple[float, ...]
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorMatch:
    score: float
    payload: dict[str, Any]


class VectorBackend(Protocol):
    def ensure_collection(self, name: str, dimension: int, distance: str) -> None: ...

    def upsert(self, name: str, points: Sequence[VectorPoint]) -> None: ...

    def count(self, name: str) -> int: ...

    def search(
        self,
        name: str,
        vector: Sequence[float],
        limit: int,
    ) -> tuple[VectorMatch, ...]: ...

    def close(self) -> None: ...


class QdrantVectorBackend:
    def __init__(self, path: str | Path = DEFAULT_QDRANT_PATH) -> None:
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as error:
            raise RuntimeError(
                'Qdrant dependencies are missing; install with pip install -e ".[vector]"'
            ) from error
        self.path = Path(path)
        self._models = models
        self._client = QdrantClient(path=str(self.path))

    def __enter__(self) -> QdrantVectorBackend:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def ensure_collection(self, name: str, dimension: int, distance: str) -> None:
        if distance != VECTOR_DISTANCE:
            raise ValueError(f"Unsupported vector distance: {distance}")
        if not self._client.collection_exists(name):
            self._client.create_collection(
                collection_name=name,
                vectors_config=self._models.VectorParams(
                    size=dimension,
                    distance=self._models.Distance.COSINE,
                ),
            )
        information = self._client.get_collection(name)
        vectors = information.config.params.vectors
        actual_dimension = getattr(vectors, "size", None)
        actual_distance = getattr(vectors, "distance", None)
        distance_value = getattr(actual_distance, "value", actual_distance)
        if actual_dimension != dimension or str(distance_value).casefold() != distance:
            raise ValueError(
                f"Collection {name} has incompatible vector configuration"
            )

    def upsert(self, name: str, points: Sequence[VectorPoint]) -> None:
        if not points:
            return
        self._client.upsert(
            collection_name=name,
            points=[
                self._models.PointStruct(
                    id=point.point_id,
                    vector=list(point.vector),
                    payload=point.payload,
                )
                for point in points
            ],
            wait=True,
        )

    def count(self, name: str) -> int:
        return int(self._client.count(name, exact=True).count)

    def search(
        self,
        name: str,
        vector: Sequence[float],
        limit: int,
    ) -> tuple[VectorMatch, ...]:
        points = self._client.query_points(
            collection_name=name,
            query=list(vector),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        ).points
        return tuple(
            VectorMatch(score=float(point.score), payload=dict(point.payload or {}))
            for point in points
        )

    def close(self) -> None:
        self._client.close()


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"enterprise-rag-lab:{chunk_id}"))


def _snapshot_identity(
    model_name: str,
    model_revision: str,
    dimension: int,
    normalized: bool,
    passage_prefix: str,
    max_sequence_length: int,
    members: Sequence[VectorIndexMember],
) -> tuple[str, str]:
    identity = "\x1f".join(
        (
            VECTOR_INDEXER_VERSION,
            model_name,
            model_revision,
            str(dimension),
            VECTOR_DISTANCE,
            str(normalized),
            passage_prefix,
            DEFAULT_QUERY_PREFIX,
            str(max_sequence_length),
            *(member.embedding_id for member in members),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"vector_{digest}", f"enterprise_rag_{digest}"


class VectorIndexService:
    def __init__(self, store: SQLiteIngestionStore, backend: VectorBackend) -> None:
        self.store = store
        self.backend = backend

    def sync_latest(self, batch_size: int = 128) -> VectorIndexResult:
        if batch_size < 1:
            raise ValueError("Vector upsert batch size must be positive")
        result, points = self._build_snapshot()
        self.backend.ensure_collection(
            result.collection_name,
            result.dimension,
            result.distance,
        )
        for start in range(0, len(points), batch_size):
            self.backend.upsert(result.collection_name, points[start : start + batch_size])
        stored_count = self.backend.count(result.collection_name)
        if stored_count != len(points):
            raise RuntimeError(
                f"Qdrant collection contains {stored_count} points, expected {len(points)}"
            )
        self.store.save_vector_index(result)
        return result

    def _build_snapshot(self) -> tuple[VectorIndexResult, tuple[VectorPoint, ...]]:
        members: list[VectorIndexMember] = []
        points: list[VectorPoint] = []
        compatibility: tuple[object, ...] | None = None
        stale_documents: list[str] = []

        for document in sorted(
            self.store.list_documents(), key=lambda item: str(item["document_id"])
        ):
            document_id = str(document["document_id"])
            source = self.store.get_latest_chunks(document_id)
            if source is None:
                continue
            chunking_id, chunks = source
            summary = self.store.inspect_embedding(document_id)
            if summary is None or summary["chunking_id"] != chunking_id:
                stale_documents.append(document_id)
                continue
            if int(summary["truncated_chunk_count"]) > 0:
                raise ValueError(
                    f"Latest embedding for {document_id} contains truncated chunks"
                )
            current_compatibility = (
                summary["model_name"],
                summary["model_revision"],
                int(summary["dimension"]),
                bool(summary["normalized"]),
                summary["passage_prefix"],
                int(summary["max_sequence_length"]),
            )
            if compatibility is None:
                compatibility = current_compatibility
            elif compatibility != current_compatibility:
                raise ValueError("Latest embeddings do not share one model space")

            embedding_id = str(summary["embedding_id"])
            embeddings = self.store.get_embeddings(embedding_id)
            if len(embeddings) != len(chunks) or any(
                embedding.chunk_id != chunk.chunk_id
                or embedding.ordinal != chunk.ordinal
                for chunk, embedding in zip(chunks, embeddings, strict=False)
            ):
                raise ValueError(
                    f"Embedding rows do not match the latest chunks for {document_id}"
                )
            member = VectorIndexMember(
                document_id=document_id,
                chunking_id=chunking_id,
                embedding_id=embedding_id,
                indexed_chunk_count=len(chunks),
            )
            members.append(member)
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                points.append(
                    VectorPoint(
                        point_id=_point_id(chunk.chunk_id),
                        vector=embedding.vector,
                        payload={
                            "chunk_id": chunk.chunk_id,
                            "document_id": document_id,
                            "chunking_id": chunking_id,
                            "embedding_id": embedding_id,
                            "ordinal": chunk.ordinal,
                            "title": str(document["title"]),
                            "text": chunk.text,
                            "heading_path": list(chunk.heading_path),
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "source_uri": document["source_uri"],
                            "source_ordinals": list(chunk.source_ordinals),
                            "previous_chunk_id": chunk.previous_chunk_id,
                            "next_chunk_id": chunk.next_chunk_id,
                        },
                    )
                )

        if stale_documents:
            raise ValueError(
                "Latest chunks are missing matching embeddings for: "
                + ", ".join(stale_documents)
            )
        if compatibility is None or not members:
            raise ValueError("No current embeddings are available for vector indexing")
        (
            model_name,
            model_revision,
            dimension,
            normalized,
            passage_prefix,
            max_sequence_length,
        ) = compatibility
        if not normalized:
            raise ValueError("Vector indexing requires L2-normalized embeddings")
        vector_index_id, collection_name = _snapshot_identity(
            str(model_name),
            str(model_revision),
            int(dimension),
            bool(normalized),
            str(passage_prefix),
            int(max_sequence_length),
            members,
        )
        result = VectorIndexResult(
            vector_index_id=vector_index_id,
            collection_name=collection_name,
            indexer_version=VECTOR_INDEXER_VERSION,
            model_name=str(model_name),
            model_revision=str(model_revision),
            dimension=int(dimension),
            distance=VECTOR_DISTANCE,
            normalized=bool(normalized),
            passage_prefix=str(passage_prefix),
            query_prefix=DEFAULT_QUERY_PREFIX,
            max_sequence_length=int(max_sequence_length),
            members=tuple(members),
        )
        return result, tuple(points)


class VectorSearchService:
    def __init__(
        self,
        store: SQLiteIngestionStore,
        backend: VectorBackend,
        encoder: QueryEmbeddingEncoder,
    ) -> None:
        self.store = store
        self.backend = backend
        self.encoder = encoder

    def search(self, query: str, limit: int = 10) -> tuple[VectorSearchResult, ...]:
        if not query.strip():
            raise ValueError("Vector query must not be blank")
        if limit < 1 or limit > 100:
            raise ValueError("Search limit must be between 1 and 100")
        index = self.store.inspect_vector_index()
        if index is None:
            raise ValueError("No vector index snapshot is available")
        expected_encoder = (
            index["model_name"],
            index["model_revision"],
            int(index["dimension"]),
            bool(index["normalized"]),
            index["query_prefix"],
            int(index["max_sequence_length"]),
        )
        actual_encoder = (
            self.encoder.model_name,
            self.encoder.model_revision,
            self.encoder.dimension,
            self.encoder.normalized,
            self.encoder.query_prefix,
            self.encoder.max_sequence_length,
        )
        if actual_encoder != expected_encoder:
            raise ValueError("Query encoder does not match the vector index model contract")
        encoded = self.encoder.encode_queries((query,), batch_size=1)
        self._validate_query(encoded)
        matches = self.backend.search(
            str(index["collection_name"]),
            encoded.vectors[0],
            limit,
        )
        return tuple(
            self._to_result(rank, str(index["vector_index_id"]), match)
            for rank, match in enumerate(matches, start=1)
        )

    def _validate_query(self, encoded: EncodedBatch) -> None:
        if len(encoded.vectors) != 1 or len(encoded.token_counts) != 1:
            raise ValueError("Query encoder must return exactly one embedding")
        vector = encoded.vectors[0]
        if len(vector) != self.encoder.dimension:
            raise ValueError("Query embedding dimension does not match the model")
        if encoded.token_counts[0] > self.encoder.max_sequence_length:
            raise ValueError("Query exceeds the embedding model token limit")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Query embedding contains a non-finite value")
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
            raise ValueError("Query embedding is not L2-normalized")

    @staticmethod
    def _to_result(
        rank: int,
        vector_index_id: str,
        match: VectorMatch,
    ) -> VectorSearchResult:
        payload = match.payload
        required = ("chunk_id", "document_id", "title", "text", "heading_path")
        if any(key not in payload for key in required):
            raise RuntimeError("Qdrant result is missing required provenance payload")
        return VectorSearchResult(
            rank=rank,
            vector_index_id=vector_index_id,
            chunk_id=str(payload["chunk_id"]),
            document_id=str(payload["document_id"]),
            title=str(payload["title"]),
            text=str(payload["text"]),
            score=match.score,
            heading_path=tuple(str(value) for value in payload["heading_path"]),
            page_start=payload.get("page_start"),
            page_end=payload.get("page_end"),
            source_uri=payload.get("source_uri"),
        )