"""Run the local Enterprise RAG Lab demo server."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from enterprise_rag_lab.demo.app import (
    DEFAULT_DATABASE,
    DEFAULT_QDRANT_PATH,
    DEFAULT_REPORTS_DIRECTORY,
    create_app,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="enterprise-rag-demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    parser.add_argument(
        "--reports-directory",
        type=Path,
        default=DEFAULT_REPORTS_DIRECTORY,
    )
    arguments = parser.parse_args()
    uvicorn.run(
        create_app(
            database=arguments.database,
            qdrant_path=arguments.qdrant_path,
            reports_directory=arguments.reports_directory,
        ),
        host=arguments.host,
        port=arguments.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()