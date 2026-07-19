"""Keyword, vector, and hybrid retrieval APIs."""

from enterprise_rag_lab.retrieval.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MODEL_REVISION,
    DEFAULT_QUERY_PREFIX,
    EMBEDDER_VERSION,
    EncodedBatch,
    EmbeddingEncoder,
    EmbeddingService,
    QueryEmbeddingEncoder,
    SentenceTransformerEncoder,
)

from enterprise_rag_lab.retrieval.keyword import (
    KEYWORD_INDEXER_VERSION,
    KEYWORD_RETRIEVER_ID,
    KEYWORD_RETRIEVER_VERSION,
    KEYWORD_TOKENIZER,
    KeywordSearchService,
)
from enterprise_rag_lab.retrieval.context import (
    CONTEXT_EXPANDER_VERSION,
    DEFAULT_MAX_CONTEXT_CHARACTERS,
    DEFAULT_NEIGHBOR_DEPTH,
    ContextExpansionService,
)
from enterprise_rag_lab.retrieval.hybrid import (
    DEFAULT_RRF_CANDIDATE_LIMIT,
    RRF_K,
    RRF_RETRIEVER_ID,
    RRF_RETRIEVER_VERSION,
    RRFSearchService,
    reciprocal_rank_fusion,
)
from enterprise_rag_lab.retrieval.vector import (
    DEFAULT_QDRANT_PATH,
    VECTOR_DISTANCE,
    VECTOR_INDEXER_VERSION,
    QdrantVectorBackend,
    VectorBackend,
    VectorIndexService,
    VectorMatch,
    VectorPoint,
    VectorSearchService,
)

__all__ = [
    "EMBEDDER_VERSION",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_MODEL_REVISION",
    "DEFAULT_QUERY_PREFIX",
    "DEFAULT_QDRANT_PATH",
    "DEFAULT_MAX_CONTEXT_CHARACTERS",
    "DEFAULT_NEIGHBOR_DEPTH",
    "DEFAULT_RRF_CANDIDATE_LIMIT",
    "CONTEXT_EXPANDER_VERSION",
    "KEYWORD_INDEXER_VERSION",
    "KEYWORD_RETRIEVER_ID",
    "KEYWORD_RETRIEVER_VERSION",
    "KEYWORD_TOKENIZER",
    "RRF_K",
    "RRF_RETRIEVER_ID",
    "RRF_RETRIEVER_VERSION",
    "VECTOR_DISTANCE",
    "VECTOR_INDEXER_VERSION",
    "EncodedBatch",
    "EmbeddingEncoder",
    "EmbeddingService",
    "ContextExpansionService",
    "KeywordSearchService",
    "QdrantVectorBackend",
    "RRFSearchService",
    "QueryEmbeddingEncoder",
    "SentenceTransformerEncoder",
    "VectorBackend",
    "VectorIndexService",
    "VectorMatch",
    "VectorPoint",
    "VectorSearchService",
    "reciprocal_rank_fusion",
]