"""
Semantic Context Manager with intelligent file selection.

This module extends the basic context management with semantic understanding,
enabling intelligent selection of relevant files based on:
- Semantic similarity
- Dependency relationships
- Access patterns
- Task relevance

Replaces the rigid 200-file limit with smart, dynamic context selection.
"""

import logging
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
import time

from .embeddings import FileEmbeddingSystem, FileEmbedding
from gambiarra.server.core.session.context import (
    ContextManager,
    FileContext,
    get_context_manager
)

logger = logging.getLogger(__name__)


@dataclass
class FileRelevanceScore:
    """Relevance score for a file in current context."""

    file_path: str
    total_score: float

    # Component scores
    semantic_score: float = 0.0
    dependency_score: float = 0.0
    access_score: float = 0.0
    recency_score: float = 0.0
    task_relevance_score: float = 0.0

    # Metadata
    reasons: List[str] = field(default_factory=list)


class SemanticContextManager:
    """
    Intelligent context manager with semantic file selection.

    Combines semantic understanding (embeddings) with traditional signals
    (dependencies, access patterns) to select the most relevant files
    for the current context.
    """

    def __init__(
        self,
        context_manager: Optional[ContextManager] = None,
        embedding_system: Optional[FileEmbeddingSystem] = None,
        max_files: int = 50,  # Much smarter limit than 200
        min_relevance_score: float = 0.3
    ):
        """
        Initialize semantic context manager.

        Args:
            context_manager: Base context manager
            embedding_system: File embedding system
            max_files: Maximum number of files to include in context
            min_relevance_score: Minimum relevance score to include a file
        """
        self.context_manager = context_manager or get_context_manager()
        self.embedding_system = embedding_system or FileEmbeddingSystem()
        self.max_files = max_files
        self.min_relevance_score = min_relevance_score

        # Cache embeddings per session
        self._session_embeddings: Dict[str, Dict[str, FileEmbedding]] = {}

        logger.info(
            f"Initialized SemanticContextManager "
            f"(max_files={max_files}, min_score={min_relevance_score})"
        )

    def select_relevant_files(
        self,
        session_id: str,
        query_files: Optional[List[str]] = None,
        task_description: Optional[str] = None,
        include_all_recent: bool = True
    ) -> List[FileRelevanceScore]:
        """
        Select most relevant files for current context.

        Args:
            session_id: Session identifier
            query_files: Files to use as query (uses recent files if None)
            task_description: Optional description of current task
            include_all_recent: Include all recently accessed files

        Returns:
            List of files with relevance scores, sorted by relevance
        """
        context = self.context_manager.get_context(session_id)
        if not context:
            logger.warning(f"No context found for session {session_id}")
            return []

        # Get query files (files we're currently working with)
        if not query_files:
            # Use most recently accessed files as query
            query_files = self._get_recent_files(session_id, limit=5)

        if not query_files:
            logger.debug("No query files, returning empty context")
            return []

        # Ensure embeddings exist for all tracked files
        self._ensure_embeddings(session_id, context.file_contexts)

        # Get embeddings for query files
        query_embeddings = [
            self._session_embeddings[session_id].get(f)
            for f in query_files
            if f in self._session_embeddings[session_id]
        ]

        if not query_embeddings:
            logger.warning("No embeddings available for query files")
            return []

        # Score all files
        file_scores = []

        for file_path, file_ctx in context.file_contexts.items():
            if file_path in query_files and include_all_recent:
                # Always include query files with high score
                score = FileRelevanceScore(
                    file_path=file_path,
                    total_score=1.0,
                    semantic_score=1.0,
                    reasons=["Currently active file"]
                )
                file_scores.append(score)
                continue

            # Compute relevance score
            relevance = self._compute_relevance(
                session_id=session_id,
                file_path=file_path,
                file_ctx=file_ctx,
                query_embeddings=query_embeddings,
                query_files=query_files,
                task_description=task_description
            )

            if relevance.total_score >= self.min_relevance_score:
                file_scores.append(relevance)

        # Sort by total score
        file_scores.sort(key=lambda x: x.total_score, reverse=True)

        # Limit to max_files
        selected = file_scores[:self.max_files]

        logger.info(
            f"Selected {len(selected)}/{len(context.file_contexts)} files "
            f"for session {session_id} (avg_score={sum(s.total_score for s in selected) / len(selected):.2f})"
        )

        return selected

    def _compute_relevance(
        self,
        session_id: str,
        file_path: str,
        file_ctx: FileContext,
        query_embeddings: List[FileEmbedding],
        query_files: List[str],
        task_description: Optional[str]
    ) -> FileRelevanceScore:
        """
        Compute relevance score for a file.

        Combines multiple signals:
        1. Semantic similarity to query files (embeddings)
        2. Dependency relationships
        3. Access patterns (frequency, recency)
        4. Task relevance
        """
        reasons = []

        # 1. Semantic similarity score (0-1)
        semantic_score = self._compute_semantic_score(
            session_id, file_path, query_embeddings
        )

        if semantic_score > 0.7:
            reasons.append(f"High semantic similarity ({semantic_score:.2f})")

        # 2. Dependency score (0-1)
        dependency_score = self._compute_dependency_score(
            session_id, file_path, query_files
        )

        if dependency_score > 0.5:
            reasons.append(f"Dependency relationship ({dependency_score:.2f})")

        # 3. Access score (0-1)
        access_score = self._compute_access_score(file_ctx)

        if access_score > 0.5:
            reasons.append(f"Frequently accessed ({access_score:.2f})")

        # 4. Recency score (0-1)
        recency_score = self._compute_recency_score(file_ctx)

        if recency_score > 0.5:
            reasons.append(f"Recently accessed ({recency_score:.2f})")

        # 5. Task relevance score (0-1)
        task_score = 0.0
        if task_description:
            task_score = self._compute_task_relevance(
                session_id, file_path, task_description
            )
            if task_score > 0.5:
                reasons.append(f"Relevant to current task ({task_score:.2f})")

        # Weighted combination
        weights = {
            'semantic': 0.35,
            'dependency': 0.25,
            'access': 0.15,
            'recency': 0.10,
            'task': 0.15
        }

        total_score = (
            weights['semantic'] * semantic_score +
            weights['dependency'] * dependency_score +
            weights['access'] * access_score +
            weights['recency'] * recency_score +
            weights['task'] * task_score
        )

        return FileRelevanceScore(
            file_path=file_path,
            total_score=total_score,
            semantic_score=semantic_score,
            dependency_score=dependency_score,
            access_score=access_score,
            recency_score=recency_score,
            task_relevance_score=task_score,
            reasons=reasons
        )

    def _compute_semantic_score(
        self,
        session_id: str,
        file_path: str,
        query_embeddings: List[FileEmbedding]
    ) -> float:
        """Compute semantic similarity score."""
        if file_path not in self._session_embeddings.get(session_id, {}):
            return 0.0

        file_embedding = self._session_embeddings[session_id][file_path]

        # Compute average similarity to all query files
        similarities = []
        for query_emb in query_embeddings:
            sim = self.embedding_system.compute_similarity(file_embedding, query_emb)
            similarities.append(sim)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _compute_dependency_score(
        self,
        session_id: str,
        file_path: str,
        query_files: List[str]
    ) -> float:
        """Compute dependency relationship score."""
        # Check if file is a dependency or dependent of query files
        dependencies = set()
        dependents = set()

        for query_file in query_files:
            dependencies.update(
                self.context_manager.get_file_dependencies(session_id, query_file)
            )
            dependents.update(
                self.context_manager.get_file_dependents(session_id, query_file)
            )

        if file_path in dependencies:
            return 1.0  # Direct dependency
        elif file_path in dependents:
            return 0.8  # Direct dependent

        # Check transitive dependencies (2 hops)
        for dep in dependencies:
            dep_deps = self.context_manager.get_file_dependencies(session_id, dep)
            if file_path in dep_deps:
                return 0.6  # Transitive dependency

        return 0.0

    def _compute_access_score(self, file_ctx: FileContext) -> float:
        """Compute access pattern score."""
        # Normalize access count (diminishing returns)
        import math

        # Log scale for access count
        if file_ctx.access_count == 0:
            return 0.0

        # Score based on log of access count
        score = min(1.0, math.log(file_ctx.access_count + 1) / math.log(20))
        return score

    def _compute_recency_score(self, file_ctx: FileContext) -> float:
        """Compute recency score."""
        # Exponential decay based on time since last access
        time_since_access = time.time() - file_ctx.last_read

        # Half-life of 1 hour (3600 seconds)
        half_life = 3600

        import math
        score = math.exp(-time_since_access * math.log(2) / half_life)

        return score

    def _compute_task_relevance(
        self,
        session_id: str,
        file_path: str,
        task_description: str
    ) -> float:
        """Compute relevance to current task."""
        if not task_description or file_path not in self._session_embeddings.get(session_id, {}):
            return 0.0

        # Embed task description
        try:
            task_embedding_vector = self.embedding_system.backend.embed_text(task_description)

            # Create temporary FileEmbedding for task
            task_embedding = FileEmbedding(
                file_path="<task>",
                embedding=task_embedding_vector,
                content_hash="",
                created_at=time.time(),
                model_name=self.embedding_system.backend.get_model_name(),
                embedding_dim=self.embedding_system.backend.get_embedding_dim()
            )

            # Compute similarity
            file_embedding = self._session_embeddings[session_id][file_path]
            return self.embedding_system.compute_similarity(task_embedding, file_embedding)

        except Exception as e:
            logger.warning(f"Error computing task relevance: {e}")
            return 0.0

    def _ensure_embeddings(
        self,
        session_id: str,
        file_contexts: Dict[str, FileContext]
    ) -> None:
        """Ensure embeddings exist for all files in context."""
        if session_id not in self._session_embeddings:
            self._session_embeddings[session_id] = {}

        # Find files that need embeddings
        files_to_embed = []

        for file_path, file_ctx in file_contexts.items():
            if file_path not in self._session_embeddings[session_id]:
                # Need to read file and generate embedding
                try:
                    path_obj = Path(file_path)
                    if path_obj.exists() and path_obj.is_file():
                        content = path_obj.read_text(errors='ignore')

                        metadata = {
                            'language': file_ctx.language,
                            'file_type': file_ctx.file_type,
                            'size': file_ctx.size
                        }

                        files_to_embed.append((file_path, content, metadata))
                except Exception as e:
                    logger.warning(f"Could not read file {file_path}: {e}")

        if not files_to_embed:
            return

        # Generate embeddings in batch for efficiency
        logger.debug(f"Generating embeddings for {len(files_to_embed)} files")

        try:
            embeddings = self.embedding_system.embed_files_batch(files_to_embed)

            for embedding in embeddings:
                self._session_embeddings[session_id][embedding.file_path] = embedding

            logger.info(f"Generated {len(embeddings)} embeddings for session {session_id}")

        except Exception as e:
            logger.error(f"Error generating embeddings: {e}", exc_info=True)

    def _get_recent_files(self, session_id: str, limit: int = 5) -> List[str]:
        """Get most recently accessed files."""
        context = self.context_manager.get_context(session_id)
        if not context:
            return []

        # Sort files by last_read time
        sorted_files = sorted(
            context.file_contexts.items(),
            key=lambda x: x[1].last_read,
            reverse=True
        )

        return [file_path for file_path, _ in sorted_files[:limit]]

    def get_context_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary of semantic context."""
        context = self.context_manager.get_context(session_id)
        if not context:
            return {}

        # Get embedding count
        embedding_count = len(self._session_embeddings.get(session_id, {}))

        # Get recent files
        recent_files = self._get_recent_files(session_id, limit=10)

        return {
            "session_id": session_id,
            "total_files": len(context.file_contexts),
            "embeddings_generated": embedding_count,
            "recent_files": recent_files,
            "max_context_files": self.max_files,
            "min_relevance_score": self.min_relevance_score
        }

    def clear_session_embeddings(self, session_id: str) -> None:
        """Clear embeddings for a session."""
        if session_id in self._session_embeddings:
            del self._session_embeddings[session_id]
            logger.debug(f"Cleared embeddings for session {session_id}")


# Global instance
_semantic_manager: Optional[SemanticContextManager] = None


def get_semantic_manager() -> SemanticContextManager:
    """Get global semantic context manager instance."""
    global _semantic_manager
    if _semantic_manager is None:
        _semantic_manager = SemanticContextManager()
    return _semantic_manager


def set_semantic_manager(manager: SemanticContextManager):
    """Set global semantic context manager instance."""
    global _semantic_manager
    _semantic_manager = manager
