from pathlib import Path

from fastapi.testclient import TestClient

from enterprise_rag_lab.demo import create_app


def _demo_app(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    return create_app(
        database=tmp_path / "demo.sqlite3",
        qdrant_path=tmp_path / "qdrant",
        reports_directory=reports,
        upload_directory=tmp_path / "uploads",
    )


def test_demo_upload_overview_and_keyword_search_use_real_pipeline(
    tmp_path: Path,
) -> None:
    app = _demo_app(tmp_path)
    content = (
        "# CORS 配置\n\n"
        "FastAPI 使用 CORSMiddleware 配置跨域资源共享、请求方法和请求头。\n"
    )

    with TestClient(app) as client:
        page = client.get("/")
        stylesheet = client.get("/assets/styles.css")
        upload = client.post(
            "/api/documents",
            files={"file": ("cors.md", content.encode("utf-8"), "text/markdown")},
        )
        overview = client.get("/api/overview")
        search = client.post(
            "/api/search",
            json={"query": "跨域资源共享", "mode": "keyword", "limit": 5},
        )

    assert page.status_code == 200
    assert "Enterprise RAG Lab" in page.text
    assert stylesheet.status_code == 200
    assert upload.status_code == 200
    assert upload.json()["chunk_count"] == 1
    assert upload.json()["table_count"] == 0
    assert overview.status_code == 200
    assert overview.json()["corpus"] == {
        "document_count": 1,
        "chunk_count": 1,
        "keyword_indexed_document_count": 1,
    }
    assert overview.json()["capabilities"]["keyword"] is True
    assert overview.json()["capabilities"]["hybrid"] is False
    assert search.status_code == 200
    assert search.json()["result_count"] == 1
    assert search.json()["results"][0]["title"] == "CORS 配置"
    assert search.json()["results"][0]["source_uri"] is None


def test_demo_hybrid_search_reports_missing_vector_snapshot(tmp_path: Path) -> None:
    app = _demo_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/search",
            json={"query": "跨域资源共享", "mode": "hybrid"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "retriever_unavailable",
        "message": "No vector index snapshot is available",
    }


def test_demo_rejects_unsupported_upload_without_persisting_it(
    tmp_path: Path,
) -> None:
    app = _demo_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            files={"file": ("notes.txt", b"not supported", "text/plain")},
        )
        overview = client.get("/api/overview")

    assert response.status_code == 415
    assert overview.json()["corpus"]["document_count"] == 0