"""Versioned embedding generation for the latest document chunks."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from enterprise_rag_lab.ingestion.store import SQLiteIngestionStore
from enterprise_rag_lab.models import ChunkEmbedding, EmbeddingResult

EMBEDDER_VERSION = "0.1.0"
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_MODEL_REVISION = "main"
DEFAULT_PASSAGE_PREFIX = "passage: "
DEFAULT_QUERY_PREFIX = "query: "


@dataclass(frozen=True, slots=True)
class EncodedBatch:
    vectors: tuple[tuple[float, ...], ...]
    token_counts: tuple[int, ...]


class EmbeddingEncoder(Protocol):
    model_name: str
    model_revision: str
    dimension: int
    normalized: bool
    passage_prefix: str
    max_sequence_length: int

    def encode_passages(self, texts: Sequence[str], batch_size: int) -> EncodedBatch: ...


class QueryEmbeddingEncoder(Protocol):
    model_name: str
    model_revision: str
    dimension: int
    normalized: bool
    query_prefix: str
    max_sequence_length: int

    def encode_queries(self, texts: Sequence[str], batch_size: int) -> EncodedBatch: ...


class SentenceTransformerEncoder:
    normalized = True
    passage_prefix = DEFAULT_PASSAGE_PREFIX
    query_prefix = DEFAULT_QUERY_PREFIX

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        model_revision: str = DEFAULT_MODEL_REVISION,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                'Embedding dependencies are missing; install with pip install -e ".[embedding]"'
            ) from error

        self.model_name = model_name
        self._model = SentenceTransformer(
            model_name,
            revision=model_revision,
            device="cpu",
            trust_remote_code=False,
        )
        first_module = self._model._first_module()
        config = getattr(getattr(first_module, "auto_model", None), "config", None)
        self.model_revision = getattr(config, "_commit_hash", None) or model_revision
        get_dimension = getattr(self._model, "get_embedding_dimension", None)
        dimension = (
            get_dimension()
            if get_dimension is not None
            else self._model.get_sentence_embedding_dimension()
        )
        if dimension is None:
            raise RuntimeError("The sentence-transformers model does not declare an embedding dimension")
        self.dimension = int(dimension)
        self.max_sequence_length = int(self._model.max_seq_length)

    def encode_passages(self, texts: Sequence[str], batch_size: int) -> EncodedBatch:
        return self._encode(texts, batch_size, self.passage_prefix)

    def encode_queries(self, texts: Sequence[str], batch_size: int) -> EncodedBatch:
        return self._encode(texts, batch_size, self.query_prefix)

    def _encode(
        self,
        texts: Sequence[str],
        batch_size: int,
        prefix: str,
    ) -> EncodedBatch:
        if not texts:
            return EncodedBatch(vectors=(), token_counts=())
        prepared = [f"{prefix}{text}" for text in texts]
        tokenizer = self._model.tokenizer
        tokenized = tokenizer(
            prepared,
            add_special_tokens=True,
            padding=False,
            truncation=False,
            verbose=False,
        )
        token_counts = tuple(len(input_ids) for input_ids in tokenized["input_ids"])
        vectors = self._model.encode(
            prepared,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=self.normalized,
        )
        return EncodedBatch(
            vectors=tuple(tuple(float(value) for value in vector) for vector in vectors),
            token_counts=token_counts,
        )


def _stable_embedding_id(chunking_id: str, encoder: EmbeddingEncoder) -> str:
    identity = "\x1f".join(
        (
            chunking_id,
            EMBEDDER_VERSION,
            encoder.model_name,
            encoder.model_revision,
            str(encoder.normalized),
            encoder.passage_prefix,
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"embedding_{digest}"


def _validate_batch(encoded: EncodedBatch, encoder: EmbeddingEncoder, expected: int) -> None:
    if encoder.dimension < 1:
        raise ValueError("Embedding dimension must be positive")
    if encoder.max_sequence_length < 1:
        raise ValueError("Embedding max sequence length must be positive")
    if len(encoded.vectors) != expected or len(encoded.token_counts) != expected:
        raise ValueError("Encoder output count does not match the input chunk count")

    for ordinal, (vector, token_count) in enumerate(
        zip(encoded.vectors, encoded.token_counts, strict=True)
    ):
        if len(vector) != encoder.dimension:
            raise ValueError(
                f"Embedding {ordinal} has dimension {len(vector)}, expected {encoder.dimension}"
            )
        if token_count < 1:
            raise ValueError(f"Embedding {ordinal} has an invalid token count")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError(f"Embedding {ordinal} contains a non-finite value")
        if encoder.normalized:
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
                raise ValueError(f"Embedding {ordinal} is not L2-normalized")


class EmbeddingService:
    def __init__(self, store: SQLiteIngestionStore, encoder: EmbeddingEncoder) -> None:
        self.store = store
        self.encoder = encoder

    def embed_document(
        self,
        document_id: str,
        batch_size: int = 32,
        allow_truncation: bool = False,
    ) -> EmbeddingResult | None:
        if batch_size < 1:
            raise ValueError("Embedding batch size must be positive")
        source = self.store.get_latest_chunks(document_id)
        if source is None:
            return None
        chunking_id, chunks = source
        encoded = self.encoder.encode_passages(
            tuple(chunk.text for chunk in chunks),
            batch_size,
        )
        _validate_batch(encoded, self.encoder, len(chunks))
        truncated_count = sum(
            token_count > self.encoder.max_sequence_length
            for token_count in encoded.token_counts
        )
        if truncated_count and not allow_truncation:
            raise ValueError(
                f"{truncated_count} chunks exceed the model limit of "
                f"{self.encoder.max_sequence_length} tokens; rechunk them or allow truncation"
            )

        result = EmbeddingResult(
            embedding_id=_stable_embedding_id(chunking_id, self.encoder),
            chunking_id=chunking_id,
            document_id=document_id,
            embedder_version=EMBEDDER_VERSION,
            model_name=self.encoder.model_name,
            model_revision=self.encoder.model_revision,
            dimension=self.encoder.dimension,
            normalized=self.encoder.normalized,
            passage_prefix=self.encoder.passage_prefix,
            max_sequence_length=self.encoder.max_sequence_length,
            embeddings=tuple(
                ChunkEmbedding(
                    chunk_id=chunk.chunk_id,
                    ordinal=chunk.ordinal,
                    vector=vector,
                    token_count=token_count,
                    truncated=token_count > self.encoder.max_sequence_length,
                )
                for chunk, vector, token_count in zip(
                    chunks,
                    encoded.vectors,
                    encoded.token_counts,
                    strict=True,
                )
            ),
        )
        self.store.save_embeddings(result)
        return result