from pathlib import Path

import pytest

import json
import sys
from types import SimpleNamespace

from enterprise_rag_lab.chunking import ChunkingService
from enterprise_rag_lab.cli import main
from enterprise_rag_lab.cleaning import CleaningService
from enterprise_rag_lab.ingestion import IngestionService, SQLiteIngestionStore
from enterprise_rag_lab.models import ChunkEmbedding, EmbeddingResult, IngestionStatus
from enterprise_rag_lab.retrieval import (
    EncodedBatch,
    EmbeddingService,
    SentenceTransformerEncoder,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeEncoder:
    model_name = "test/model"
    model_revision = "revision-1"
    dimension = 3
    normalized = True
    passage_prefix = "passage: "
    max_sequence_length = 4

    def __init__(self, *_args) -> None:
        pass

    def encode_passages(self, texts, batch_size: int) -> EncodedBatch:
        assert batch_size == 2
        return EncodedBatch(
            vectors=tuple((0.6, 0.8, 0.0) for _ in texts),
            token_counts=tuple(5 if ordinal == 0 else 3 for ordinal, _ in enumerate(texts)),
        )


def test_embedding_store_replays_float32_vectors_and_audit_metadata(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "embedding.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    assert run.status is IngestionStatus.SUCCEEDED
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None

    embeddings = tuple(
        ChunkEmbedding(
            chunk_id=chunk.chunk_id,
            ordinal=chunk.ordinal,
            vector=(0.6, 0.8, 0.0),
            token_count=20 + chunk.ordinal,
            truncated=chunk.ordinal == 0,
        )
        for chunk in chunking.chunks
    )
    result = EmbeddingResult(
        embedding_id="embedding_test",
        chunking_id=chunking.chunking_id,
        document_id=document_id,
        embedder_version="test",
        model_name="test/model",
        model_revision="revision-1",
        dimension=3,
        normalized=True,
        passage_prefix="passage: ",
        max_sequence_length=32,
        embeddings=embeddings,
    )

    store.save_embeddings(result)
    store.save_embeddings(result)

    restored = store.get_embeddings(result.embedding_id)
    assert len(restored) == len(embeddings)
    assert restored[0].vector == pytest.approx((0.6, 0.8, 0.0))
    assert restored[0].truncated is True
    summary = store.inspect_embedding(document_id)
    assert summary is not None
    assert summary["embedded_chunk_count"] == len(embeddings)
    assert summary["truncated_chunk_count"] == 1
    assert summary["dimension"] == 3
    assert summary["normalized"] is True


def test_embedding_service_validates_and_replays_latest_chunks(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "embedding.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    chunking = ChunkingService(store).chunk_document(document_id)
    assert chunking is not None
    service = EmbeddingService(store, FakeEncoder())

    first = service.embed_document(document_id, batch_size=2, allow_truncation=True)
    second = service.embed_document(document_id, batch_size=2, allow_truncation=True)

    assert first is not None
    assert second == first
    assert first.embedding_id.startswith("embedding_")
    assert len(first.embeddings) == len(chunking.chunks)
    assert first.embeddings[0].truncated is True
    assert all(len(item.vector) == 3 for item in first.embeddings)
    summary = store.inspect_embedding(document_id)
    assert summary is not None
    assert summary["embedding_id"] == first.embedding_id
    assert summary["embedded_chunk_count"] == len(chunking.chunks)


def test_embedding_cli_prints_summary_without_vectors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    database = tmp_path / "embedding.sqlite3"
    store = SQLiteIngestionStore(database)
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    assert ChunkingService(store).chunk_document(document_id) is not None
    monkeypatch.setattr("enterprise_rag_lab.cli.SentenceTransformerEncoder", FakeEncoder)

    exit_code = main(
        [
            "--database",
            str(database),
            "embed-document",
            document_id,
            "--batch-size",
            "2",
            "--allow-truncation",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["model_name"] == "test/model"
    assert payload["dimension"] == 3
    assert payload["embedded_chunk_count"] > 0
    assert "embeddings" not in payload

    exit_code = main(["--database", str(database), "inspect-embedding", document_id])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["embedding_id"].startswith("embedding_")


def test_sentence_transformer_encoder_applies_e5_passage_contract(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeTokenizer:
        def __call__(self, texts, **kwargs):
            calls["tokenizer_texts"] = texts
            calls["tokenizer_options"] = kwargs
            return {
                "input_ids": [
                    [1, 2, 3] if ordinal == 0 else [1, 2, 3, 4, 5]
                    for ordinal, _ in enumerate(texts)
                ]
            }

    class FakeSentenceTransformer:
        tokenizer = FakeTokenizer()
        max_seq_length = 4

        def __init__(self, model_name, **kwargs) -> None:
            calls["model_name"] = model_name
            calls["model_options"] = kwargs

        def _first_module(self):
            config = SimpleNamespace(_commit_hash="resolved-commit")
            return SimpleNamespace(auto_model=SimpleNamespace(config=config))

        def get_sentence_embedding_dimension(self):
            return 3

        def encode(self, texts, **kwargs):
            calls["encode_texts"] = texts
            calls["encode_options"] = kwargs
            return tuple(
                (1.0, 0.0, 0.0) if ordinal == 0 else (0.0, 1.0, 0.0)
                for ordinal, _ in enumerate(texts)
            )

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    encoder = SentenceTransformerEncoder("test/e5", "requested-revision")
    encoded = encoder.encode_passages(("第一段", "second passage"), batch_size=2)

    assert encoder.model_revision == "resolved-commit"
    assert encoder.dimension == 3
    assert encoded.token_counts == (3, 5)
    assert calls["tokenizer_texts"] == ["passage: 第一段", "passage: second passage"]
    assert calls["encode_texts"] == calls["tokenizer_texts"]
    assert calls["model_options"] == {
        "revision": "requested-revision",
        "device": "cpu",
        "trust_remote_code": False,
    }
    assert calls["tokenizer_options"] == {
        "add_special_tokens": True,
        "padding": False,
        "truncation": False,
        "verbose": False,
    }
    assert calls["encode_options"] == {
        "batch_size": 2,
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "normalize_embeddings": True,
    }

    query = encoder.encode_queries(("如何配置跨域",), batch_size=1)

    assert query.token_counts == (3,)
    assert calls["tokenizer_texts"] == ["query: 如何配置跨域"]
    assert calls["encode_texts"] == calls["tokenizer_texts"]
    assert calls["encode_options"] == {
        "batch_size": 1,
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "normalize_embeddings": True,
    }


def test_embedding_service_rejects_truncation_by_default(tmp_path: Path) -> None:
    store = SQLiteIngestionStore(tmp_path / "embedding.sqlite3")
    run = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md"
    )
    document_id = run.document_id or ""
    assert CleaningService(store).clean_document(document_id) is not None
    assert ChunkingService(store).chunk_document(document_id) is not None

    with pytest.raises(ValueError, match="exceed the model limit"):
        EmbeddingService(store, FakeEncoder()).embed_document(document_id, batch_size=2)

    assert store.inspect_embedding(document_id) is None


def test_embed_all_cli_summarizes_documents_and_truncation(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    database = tmp_path / "embedding.sqlite3"
    store = SQLiteIngestionStore(database)
    sources = (
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/cors.md",
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/first-steps.md",
    )
    for source in sources:
        run = IngestionService(store).ingest(source)
        document_id = run.document_id or ""
        assert CleaningService(store).clean_document(document_id) is not None
        assert ChunkingService(store).chunk_document(document_id) is not None
    missing_chunks = IngestionService(store).ingest(
        PROJECT_ROOT / "data/raw/fastapi/docs/tutorial/index.md"
    )
    missing_chunks_document_id = missing_chunks.document_id or ""
    monkeypatch.setattr("enterprise_rag_lab.cli.SentenceTransformerEncoder", FakeEncoder)

    exit_code = main(
        [
            "--database",
            str(database),
            "embed-all",
            "--batch-size",
            "2",
            "--allow-truncation",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["document_count"] == 3
    assert payload["succeeded_document_count"] == 2
    assert payload["failed_document_count"] == 1
    assert payload["embedded_chunk_count"] > 2
    assert payload["truncated_chunk_count"] == 2
    assert payload["failures"] == [
        {
            "document_id": missing_chunks_document_id,
            "message": "No chunking version is available",
        }
    ]