"""
File context tracker for Gambiarra client.
Tracks file modifications and provides freshness information to prevent stale context issues.
Provides intelligent file context tracking and analysis.
"""

import os
import logging
from typing import Dict, Set, Optional, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context information for a tracked file."""
    path: str
    last_read: Optional[datetime]
    last_modified: Optional[datetime]
    last_content_hash: Optional[str]
    modification_count: int
    is_stale: bool = False


class FileContextTracker:
    """
    Tracks file context to prevent stale information issues.
    Monitors files that have been read or modified and alerts when context may be stale.
    """

    def __init__(self, max_tracked_files: int = 100):
        self.max_tracked_files = max_tracked_files
        self.tracked_files: Dict[str, FileContext] = {}
        self.modified_files: Set[str] = set()
        self.session_start = datetime.now()

        logger.info(f"📁 File context tracker initialized (max files: {max_tracked_files})")

    def track_file_read(self, file_path: str, content: str = None) -> None:
        """
        Track that a file has been read.

        Args:
            file_path: Path to the file
            content: Optional file content for hash calculation
        """
        abs_path = os.path.abspath(file_path)

        try:
            stat = os.stat(abs_path)
            mtime = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            mtime = None

        content_hash = None
        if content:
            import hashlib
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        if abs_path in self.tracked_files:
            context = self.tracked_files[abs_path]
            context.last_read = datetime.now()
            context.last_modified = mtime
            context.last_content_hash = content_hash
            context.is_stale = False
        else:
            context = FileContext(
                path=abs_path,
                last_read=datetime.now(),
                last_modified=mtime,
                last_content_hash=content_hash,
                modification_count=0,
                is_stale=False
            )
            self.tracked_files[abs_path] = context
            self._enforce_limit()

        logger.debug(f"📖 Tracked file read: {abs_path}")

    def track_file_write(self, file_path: str, content: str = None) -> None:
        """
        Track that a file has been written/modified.

        Args:
            file_path: Path to the file
            content: Optional new content for hash calculation
        """
        abs_path = os.path.abspath(file_path)

        content_hash = None
        if content:
            import hashlib
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        if abs_path in self.tracked_files:
            context = self.tracked_files[abs_path]
            context.last_modified = datetime.now()
            context.last_content_hash = content_hash
            context.modification_count += 1
            # Mark as stale since it was modified after being read
            context.is_stale = True
        else:
            context = FileContext(
                path=abs_path,
                last_read=None,
                last_modified=datetime.now(),
                last_content_hash=content_hash,
                modification_count=1,
                is_stale=False
            )
            self.tracked_files[abs_path] = context
            self._enforce_limit()

        self.modified_files.add(abs_path)
        logger.debug(f"✏️ Tracked file write: {abs_path}")

    def check_file_freshness(self, file_path: str) -> Dict[str, any]:
        """
        Check if file context is fresh or stale.

        Args:
            file_path: Path to check

        Returns:
            Dict with freshness information
        """
        abs_path = os.path.abspath(file_path)

        if abs_path not in self.tracked_files:
            return {
                "tracked": False,
                "stale": False,
                "reason": "File not tracked"
            }

        context = self.tracked_files[abs_path]

        # Check if file has been modified on disk since last read
        try:
            stat = os.stat(abs_path)
            disk_mtime = datetime.fromtimestamp(stat.st_mtime)

            if context.last_read and context.last_modified:
                if disk_mtime > context.last_read:
                    context.is_stale = True
                    return {
                        "tracked": True,
                        "stale": True,
                        "reason": "File modified on disk since last read",
                        "last_read": context.last_read.isoformat(),
                        "disk_modified": disk_mtime.isoformat()
                    }
        except OSError:
            pass

        if context.is_stale:
            return {
                "tracked": True,
                "stale": True,
                "reason": "File modified by tool after being read",
                "modification_count": context.modification_count
            }

        return {
            "tracked": True,
            "stale": False,
            "reason": "File context is fresh",
            "last_read": context.last_read.isoformat() if context.last_read else None,
            "modification_count": context.modification_count
        }

    def get_stale_files(self) -> List[str]:
        """
        Get list of files with stale context.

        Returns:
            List of file paths that have stale context
        """
        stale_files = []

        for path, context in self.tracked_files.items():
            if context.is_stale:
                stale_files.append(path)
            elif os.path.exists(path):
                # Check disk modification time
                try:
                    stat = os.stat(path)
                    disk_mtime = datetime.fromtimestamp(stat.st_mtime)
                    if context.last_read and context.last_modified:
                        if disk_mtime > context.last_read:
                            context.is_stale = True
                            stale_files.append(path)
                except OSError:
                    pass

        return stale_files

    def get_modified_files(self) -> Set[str]:
        """
        Get set of files modified during this session.

        Returns:
            Set of modified file paths
        """
        return self.modified_files.copy()

    def mark_file_fresh(self, file_path: str) -> None:
        """
        Mark a file's context as fresh (not stale).

        Args:
            file_path: Path to mark as fresh
        """
        abs_path = os.path.abspath(file_path)
        if abs_path in self.tracked_files:
            self.tracked_files[abs_path].is_stale = False
            logger.debug(f"✨ Marked file context as fresh: {abs_path}")

    def clear_stale_files(self) -> None:
        """Clear all stale file markers."""
        for context in self.tracked_files.values():
            context.is_stale = False
        logger.info("🔄 Cleared all stale file markers")

    def _enforce_limit(self) -> None:
        """Enforce maximum number of tracked files."""
        if len(self.tracked_files) > self.max_tracked_files:
            # Remove oldest read files first
            sorted_files = sorted(
                self.tracked_files.items(),
                key=lambda x: x[1].last_read or self.session_start
            )

            to_remove = len(self.tracked_files) - self.max_tracked_files
            for path, _ in sorted_files[:to_remove]:
                del self.tracked_files[path]
                self.modified_files.discard(path)

            logger.debug(f"🗑️ Removed {to_remove} old tracked files")

    def get_context_summary(self) -> Dict[str, any]:
        """
        Get summary of current context state.

        Returns:
            Dict with context statistics
        """
        stale_count = sum(1 for c in self.tracked_files.values() if c.is_stale)

        return {
            "tracked_files": len(self.tracked_files),
            "modified_files": len(self.modified_files),
            "stale_files": stale_count,
            "max_tracked": self.max_tracked_files,
            "session_duration": (datetime.now() - self.session_start).total_seconds()
        }

    def suggest_refresh(self) -> List[str]:
        """
        Suggest files that should be refreshed due to staleness.

        Returns:
            List of file paths that should be re-read
        """
        suggestions = []

        for path, context in self.tracked_files.items():
            if context.is_stale and context.last_read:
                # Only suggest files that were actually read before
                suggestions.append(path)

        # Sort by modification count (most modified first)
        suggestions.sort(
            key=lambda p: self.tracked_files[p].modification_count,
            reverse=True
        )

        return suggestions[:5]  # Return top 5 suggestions