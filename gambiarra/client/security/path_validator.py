"""
Path validation and security for Gambiarra client.
Prevents directory traversal and enforces workspace boundaries.
"""

import os
import fnmatch
from pathlib import Path
from typing import List, Set
import logging

logger = logging.getLogger(__name__)


class PathValidator:
    """Validates file paths and enforces security boundaries."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.ignore_patterns: List[str] = []
        self._load_ignore_patterns()

    def _load_ignore_patterns(self) -> None:
        """Load .gambiarraignore patterns."""
        ignore_file = self.workspace_root / ".gambiarraignore"

        if ignore_file.exists():
            try:
                with open(ignore_file, 'r') as f:
                    patterns = [
                        line.strip() for line in f
                        if line.strip() and not line.startswith('#')
                    ]
                self.ignore_patterns.extend(patterns)
                logger.info(f"📁 Loaded {len(patterns)} ignore patterns from .gambiarraignore")
            except Exception as e:
                logger.warning(f"❌ Failed to load .gambiarraignore: {e}")

        # Add default ignore patterns
        default_patterns = [
            ".git/**",
            ".git",
            "node_modules/**",
            "node_modules",
            "__pycache__/**",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".env",
            ".env.*",
            "*.log",
            ".DS_Store",
            "Thumbs.db"
        ]

        self.ignore_patterns.extend(default_patterns)
        logger.info(f"📁 Total ignore patterns: {len(self.ignore_patterns)}")

    def validate_path(self, input_path: str) -> str:
        """Validate and resolve path within workspace."""
        try:
            # Convert to Path object
            path = Path(input_path)

            # Resolve to absolute path
            if path.is_absolute():
                absolute_path = path.resolve()
            else:
                absolute_path = (self.workspace_root / path).resolve()

            # Check if path is within workspace
            try:
                absolute_path.relative_to(self.workspace_root)
            except ValueError:
                raise SecurityError(
                    f"Path traversal detected: '{input_path}' resolves outside workspace",
                    {
                        "input_path": input_path,
                        "resolved_path": str(absolute_path),
                        "workspace_root": str(self.workspace_root)
                    }
                )

            # Check against ignore patterns
            relative_path = absolute_path.relative_to(self.workspace_root)
            if self.is_ignored(str(relative_path)):
                raise SecurityError(
                    f"Access denied by ignore patterns: '{input_path}'",
                    {
                        "input_path": input_path,
                        "relative_path": str(relative_path),
                        "matching_patterns": self._get_matching_patterns(str(relative_path))
                    }
                )

            return str(absolute_path)

        except SecurityError:
            raise
        except Exception as e:
            raise SecurityError(
                f"Path validation error: {e}",
                {"input_path": input_path}
            )

    def is_ignored(self, relative_path: str) -> bool:
        """Check if path matches ignore patterns."""
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(relative_path, pattern):
                return True

            # Check if any parent directory matches
            path_parts = Path(relative_path).parts
            for i in range(len(path_parts)):
                partial_path = "/".join(path_parts[:i+1])
                if fnmatch.fnmatch(partial_path, pattern):
                    return True

        return False

    def _get_matching_patterns(self, relative_path: str) -> List[str]:
        """Get all patterns that match the given path."""
        matching = []
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(relative_path, pattern):
                matching.append(pattern)
        return matching

    def validate_multiple_paths(self, paths: List[str]) -> List[str]:
        """Validate multiple paths at once."""
        validated_paths = []
        for path in paths:
            validated_paths.append(self.validate_path(path))
        return validated_paths

    def is_within_workspace(self, path: str) -> bool:
        """Check if path is within workspace without raising exceptions."""
        try:
            self.validate_path(path)
            return True
        except SecurityError:
            return False

    def get_relative_path(self, absolute_path: str) -> str:
        """Get relative path from workspace root."""
        try:
            abs_path = Path(absolute_path).resolve()
            return str(abs_path.relative_to(self.workspace_root))
        except ValueError:
            raise SecurityError(
                f"Path '{absolute_path}' is not within workspace",
                {"absolute_path": absolute_path, "workspace_root": str(self.workspace_root)}
            )

    def list_allowed_files(self, directory: str = ".", pattern: str = "*") -> List[str]:
        """List files that are not ignored by patterns."""
        try:
            dir_path = Path(self.validate_path(directory))
            allowed_files = []

            for file_path in dir_path.rglob(pattern):
                if file_path.is_file():
                    relative_path = str(file_path.relative_to(self.workspace_root))
                    if not self.is_ignored(relative_path):
                        allowed_files.append(str(file_path))

            return sorted(allowed_files)

        except Exception as e:
            logger.error(f"❌ Error listing files: {e}")
            return []

    def add_ignore_pattern(self, pattern: str) -> None:
        """Add a new ignore pattern."""
        if pattern not in self.ignore_patterns:
            self.ignore_patterns.append(pattern)
            logger.info(f"📁 Added ignore pattern: {pattern}")

    def remove_ignore_pattern(self, pattern: str) -> bool:
        """Remove an ignore pattern."""
        try:
            self.ignore_patterns.remove(pattern)
            logger.info(f"📁 Removed ignore pattern: {pattern}")
            return True
        except ValueError:
            return False

    def get_workspace_info(self) -> dict:
        """Get information about the workspace."""
        return {
            "workspace_root": str(self.workspace_root),
            "exists": self.workspace_root.exists(),
            "is_directory": self.workspace_root.is_dir(),
            "ignore_patterns_count": len(self.ignore_patterns),
            "has_gambiarraignore": (self.workspace_root / ".gambiarraignore").exists()
        }


class SecurityError(Exception):
    """Security-related path validation error."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "error": "SECURITY_ERROR",
            "message": self.message,
            "details": self.details
        }