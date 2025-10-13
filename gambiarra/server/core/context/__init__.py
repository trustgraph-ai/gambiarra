"""
Enhanced Context Management with Semantic Understanding.

This package provides intelligent file selection and context management
using semantic embeddings and relevance scoring.
"""

from .embeddings import (
    FileEmbedding,
    EmbeddingBackend,
    SentenceTransformerBackend,
    SimpleEmbeddingBackend,
    FileEmbeddingSystem
)

from .semantic_manager import (
    FileRelevanceScore,
    SemanticContextManager,
    get_semantic_manager,
    set_semantic_manager
)

__all__ = [
    # Embeddings
    'FileEmbedding',
    'EmbeddingBackend',
    'SentenceTransformerBackend',
    'SimpleEmbeddingBackend',
    'FileEmbeddingSystem',

    # Semantic Management
    'FileRelevanceScore',
    'SemanticContextManager',
    'get_semantic_manager',
    'set_semantic_manager',
]
