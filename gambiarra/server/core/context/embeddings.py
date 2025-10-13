"""
File Embedding System for Semantic Context Management.

This module provides semantic understanding of code files through embeddings,
enabling intelligent file selection based on relevance rather than just
dependency analysis or access patterns.

Key features:
- Generate embeddings for code files
- Compute semantic similarity between files
- Cache embeddings for performance
- Support multiple embedding backends (local models, API services)
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FileEmbedding:
    """Represents the embedding of a file."""

    file_path: str
    embedding: np.ndarray
    content_hash: str
    created_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Embedding details
    model_name: str = "sentence-transformers"
    embedding_dim: int = 384


class EmbeddingBackend:
    """Abstract base class for embedding backends."""

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as numpy array
        """
        raise NotImplementedError

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        return [self.embed_text(text) for text in texts]

    def get_embedding_dim(self) -> int:
        """Get the dimensionality of embeddings."""
        raise NotImplementedError

    def get_model_name(self) -> str:
        """Get the name of the embedding model."""
        raise NotImplementedError


class SentenceTransformerBackend(EmbeddingBackend):
    """
    Embedding backend using sentence-transformers library.

    Uses lightweight models that run locally without API calls.
    Good balance between quality and speed.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize sentence transformer backend.

        Args:
            model_name: Name of sentence-transformers model
                       "all-MiniLM-L6-v2" (default) - Fast, 384 dimensions
                       "all-mpnet-base-v2" - Better quality, 768 dimensions
        """
        self.model_name = model_name
        self._model = None
        self._embedding_dim = 384 if "MiniLM" in model_name else 768

    def _ensure_model(self):
        """Lazy load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model: {self.model_name}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to load embedding model: {e}")

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text."""
        self._ensure_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts (more efficient)."""
        self._ensure_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [embeddings[i] for i in range(len(texts))]

    def get_embedding_dim(self) -> int:
        """Get embedding dimensionality."""
        return self._embedding_dim

    def get_model_name(self) -> str:
        """Get model name."""
        return self.model_name


class SimpleEmbeddingBackend(EmbeddingBackend):
    """
    Simple embedding backend using TF-IDF-like approach.

    Falls back to this if sentence-transformers is not available.
    Much faster but lower quality than transformer models.
    """

    def __init__(self, embedding_dim: int = 100):
        """Initialize simple backend."""
        self.embedding_dim = embedding_dim
        self.model_name = "simple-tfidf"

    def embed_text(self, text: str) -> np.ndarray:
        """Generate simple embedding for text."""
        # Create a simple hash-based embedding
        # This is a fallback and not very sophisticated
        words = text.lower().split()

        # Create embedding from character and word features
        embedding = np.zeros(self.embedding_dim)

        for i, word in enumerate(words[:50]):  # Use first 50 words
            # Hash word to indices
            word_hash = hash(word)
            idx1 = abs(word_hash) % self.embedding_dim
            idx2 = abs(word_hash // self.embedding_dim) % self.embedding_dim

            # Increment embedding at hashed positions
            embedding[idx1] += 1.0 / (i + 1)  # Weight by position
            embedding[idx2] += 0.5 / (i + 1)

        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def get_embedding_dim(self) -> int:
        """Get embedding dimensionality."""
        return self.embedding_dim

    def get_model_name(self) -> str:
        """Get model name."""
        return self.model_name


class FileEmbeddingSystem:
    """
    System for generating and managing file embeddings.

    Provides semantic understanding of code files through embeddings,
    with caching for performance.
    """

    def __init__(
        self,
        backend: Optional[EmbeddingBackend] = None,
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize file embedding system.

        Args:
            backend: Embedding backend to use (auto-selects if None)
            cache_dir: Directory for caching embeddings
        """
        self.backend = backend or self._create_default_backend()
        self.cache_dir = cache_dir or Path.home() / ".cache" / "gambiarra" / "embeddings"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._embedding_cache: Dict[str, FileEmbedding] = {}

        logger.info(
            f"Initialized FileEmbeddingSystem with {self.backend.get_model_name()} "
            f"(dim={self.backend.get_embedding_dim()})"
        )

    def _create_default_backend(self) -> EmbeddingBackend:
        """Create default embedding backend."""
        try:
            # Try sentence-transformers first
            return SentenceTransformerBackend()
        except (ImportError, RuntimeError) as e:
            logger.warning(
                f"Could not load sentence-transformers ({e}), "
                f"falling back to simple embedding"
            )
            return SimpleEmbeddingBackend()

    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of file content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_cache_path(self, file_path: str, content_hash: str) -> Path:
        """Get path to cached embedding file."""
        # Create safe filename from file path
        safe_name = hashlib.md5(file_path.encode()).hexdigest()
        return self.cache_dir / f"{safe_name}_{content_hash}.json"

    def _load_from_cache(self, file_path: str, content_hash: str) -> Optional[FileEmbedding]:
        """Load embedding from cache."""
        # Check memory cache first
        cache_key = f"{file_path}:{content_hash}"
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # Check disk cache
        cache_path = self._get_cache_path(file_path, content_hash)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)

            embedding = FileEmbedding(
                file_path=data['file_path'],
                embedding=np.array(data['embedding']),
                content_hash=data['content_hash'],
                created_at=data['created_at'],
                metadata=data.get('metadata', {}),
                model_name=data.get('model_name', 'unknown'),
                embedding_dim=data.get('embedding_dim', len(data['embedding']))
            )

            # Add to memory cache
            self._embedding_cache[cache_key] = embedding

            return embedding

        except Exception as e:
            logger.warning(f"Failed to load cached embedding for {file_path}: {e}")
            return None

    def _save_to_cache(self, embedding: FileEmbedding) -> None:
        """Save embedding to cache."""
        cache_key = f"{embedding.file_path}:{embedding.content_hash}"

        # Save to memory cache
        self._embedding_cache[cache_key] = embedding

        # Save to disk cache
        try:
            cache_path = self._get_cache_path(embedding.file_path, embedding.content_hash)

            data = {
                'file_path': embedding.file_path,
                'embedding': embedding.embedding.tolist(),
                'content_hash': embedding.content_hash,
                'created_at': embedding.created_at,
                'metadata': embedding.metadata,
                'model_name': embedding.model_name,
                'embedding_dim': embedding.embedding_dim
            }

            with open(cache_path, 'w') as f:
                json.dump(data, f)

        except Exception as e:
            logger.warning(f"Failed to cache embedding for {embedding.file_path}: {e}")

    def embed_file(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> FileEmbedding:
        """
        Generate embedding for a file.

        Args:
            file_path: Path to the file
            content: File content
            metadata: Optional metadata about the file

        Returns:
            FileEmbedding object
        """
        import time

        # Compute content hash
        content_hash = self._compute_content_hash(content)

        # Try to load from cache
        cached = self._load_from_cache(file_path, content_hash)
        if cached is not None:
            logger.debug(f"Loaded cached embedding for {file_path}")
            return cached

        # Generate new embedding
        logger.debug(f"Generating embedding for {file_path}")

        # Preprocess content for embedding
        processed_content = self._preprocess_content(content, file_path)

        # Generate embedding
        embedding_vector = self.backend.embed_text(processed_content)

        # Create FileEmbedding object
        embedding = FileEmbedding(
            file_path=file_path,
            embedding=embedding_vector,
            content_hash=content_hash,
            created_at=time.time(),
            metadata=metadata or {},
            model_name=self.backend.get_model_name(),
            embedding_dim=self.backend.get_embedding_dim()
        )

        # Save to cache
        self._save_to_cache(embedding)

        return embedding

    def embed_files_batch(
        self,
        files: List[Tuple[str, str, Optional[Dict[str, Any]]]]
    ) -> List[FileEmbedding]:
        """
        Generate embeddings for multiple files efficiently.

        Args:
            files: List of (file_path, content, metadata) tuples

        Returns:
            List of FileEmbedding objects
        """
        import time

        embeddings = []
        to_embed = []  # Files that need new embeddings
        to_embed_indices = []

        # Check cache for each file
        for i, (file_path, content, metadata) in enumerate(files):
            content_hash = self._compute_content_hash(content)
            cached = self._load_from_cache(file_path, content_hash)

            if cached is not None:
                embeddings.append(cached)
            else:
                # Need to generate embedding
                to_embed.append((file_path, content, metadata, content_hash))
                to_embed_indices.append(i)
                embeddings.append(None)  # Placeholder

        if not to_embed:
            return embeddings

        # Generate embeddings in batch
        logger.debug(f"Generating embeddings for {len(to_embed)} files")

        processed_contents = [
            self._preprocess_content(content, path)
            for path, content, _, _ in to_embed
        ]

        embedding_vectors = self.backend.embed_batch(processed_contents)

        # Create FileEmbedding objects and fill in placeholders
        for idx, (file_path, _, metadata, content_hash) in enumerate(to_embed):
            embedding = FileEmbedding(
                file_path=file_path,
                embedding=embedding_vectors[idx],
                content_hash=content_hash,
                created_at=time.time(),
                metadata=metadata or {},
                model_name=self.backend.get_model_name(),
                embedding_dim=self.backend.get_embedding_dim()
            )

            self._save_to_cache(embedding)

            # Fill in placeholder
            embeddings[to_embed_indices[idx]] = embedding

        return embeddings

    def _preprocess_content(self, content: str, file_path: str) -> str:
        """
        Preprocess file content for embedding.

        Extracts meaningful text from code, focusing on:
        - Function/class names and signatures
        - Comments and docstrings
        - Import statements
        - Key identifiers
        """
        # For now, use a simple approach: take first 1000 characters
        # plus extract function/class definitions and comments

        lines = content.split('\n')
        important_lines = []

        # Extract imports, function defs, class defs, comments
        for line in lines[:200]:  # First 200 lines
            stripped = line.strip()

            # Keep import statements
            if any(stripped.startswith(kw) for kw in ['import ', 'from ', 'package ', '#include']):
                important_lines.append(stripped)

            # Keep function/class definitions
            elif any(kw in stripped for kw in ['def ', 'class ', 'function ', 'interface ', 'struct ']):
                important_lines.append(stripped)

            # Keep comments and docstrings
            elif stripped.startswith(('#', '//', '"""', "'''",' *', '/*')):
                important_lines.append(stripped)

        # Combine with truncated content
        important_text = '\n'.join(important_lines)
        truncated_content = content[:1000]

        # Add file name for context
        file_name = Path(file_path).name

        return f"File: {file_name}\n\n{important_text}\n\n{truncated_content}"

    def compute_similarity(
        self,
        embedding1: FileEmbedding,
        embedding2: FileEmbedding
    ) -> float:
        """
        Compute cosine similarity between two file embeddings.

        Args:
            embedding1: First file embedding
            embedding2: Second file embedding

        Returns:
            Similarity score between 0 and 1
        """
        # Cosine similarity
        dot_product = np.dot(embedding1.embedding, embedding2.embedding)
        norm1 = np.linalg.norm(embedding1.embedding)
        norm2 = np.linalg.norm(embedding2.embedding)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, (similarity + 1) / 2))

    def find_similar_files(
        self,
        query_embedding: FileEmbedding,
        candidate_embeddings: List[FileEmbedding],
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Find most similar files to a query file.

        Args:
            query_embedding: Embedding of query file
            candidate_embeddings: List of candidate file embeddings
            top_k: Number of top results to return

        Returns:
            List of (file_path, similarity_score) tuples, sorted by score descending
        """
        similarities = []

        for candidate in candidate_embeddings:
            if candidate.file_path == query_embedding.file_path:
                continue  # Skip self

            similarity = self.compute_similarity(query_embedding, candidate)
            similarities.append((candidate.file_path, similarity))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def clear_cache(self) -> int:
        """
        Clear embedding cache.

        Returns:
            Number of cache entries cleared
        """
        # Clear memory cache
        count = len(self._embedding_cache)
        self._embedding_cache.clear()

        # Clear disk cache
        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {cache_file}: {e}")

        logger.info(f"Cleared {count} embeddings from cache")
        return count
