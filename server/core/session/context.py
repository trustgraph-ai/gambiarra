"""
Enhanced session context management.
Provides rich conversation context tracking based on KiloCode patterns.
"""

import logging
import time
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context information about a file."""
    path: str
    last_read: float
    last_modified: float
    size: int
    content_hash: str
    access_count: int = 0
    is_stale: bool = False


@dataclass
class ToolCall:
    """Record of a tool call."""
    tool_name: str
    parameters: Dict[str, Any]
    timestamp: float
    result: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None


@dataclass
class ConversationContext:
    """Rich conversation context for a session."""
    session_id: str
    working_directory: str

    # File tracking
    file_contexts: Dict[str, FileContext] = field(default_factory=dict)
    watched_files: Set[str] = field(default_factory=set)

    # Tool tracking
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_count: Dict[str, int] = field(default_factory=dict)

    # Context memory
    token_count: int = 0
    max_tokens: int = 100000
    context_window_used: float = 0.0

    # State tracking
    current_task: Optional[str] = None
    task_progress: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class ContextManager:
    """Manages conversation context and memory optimization."""

    def __init__(self, max_contexts: int = 1000):
        self.contexts: Dict[str, ConversationContext] = {}
        self.max_contexts = max_contexts

    def create_context(self, session_id: str, working_directory: str = ".") -> ConversationContext:
        """Create new conversation context."""
        context = ConversationContext(
            session_id=session_id,
            working_directory=working_directory
        )

        self.contexts[session_id] = context

        # Cleanup old contexts if needed
        if len(self.contexts) > self.max_contexts:
            self._cleanup_old_contexts()

        logger.debug(f"📝 Created context for session {session_id}")
        return context

    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation context."""
        context = self.contexts.get(session_id)
        if context:
            context.last_activity = time.time()
        return context

    def track_file_access(self, session_id: str, file_path: str, content: str) -> None:
        """Track file access for context management."""
        context = self.get_context(session_id)
        if not context:
            return

        # Calculate content hash for staleness detection
        content_hash = str(hash(content))

        # Get file stats
        try:
            path_obj = Path(file_path)
            if path_obj.exists():
                stat = path_obj.stat()
                last_modified = stat.st_mtime
                size = stat.st_size
            else:
                last_modified = time.time()
                size = len(content)
        except:
            last_modified = time.time()
            size = len(content)

        # Update or create file context
        if file_path in context.file_contexts:
            file_ctx = context.file_contexts[file_path]
            file_ctx.last_read = time.time()
            file_ctx.access_count += 1

            # Check if file is stale (modified since last read)
            if file_ctx.last_modified != last_modified or file_ctx.content_hash != content_hash:
                file_ctx.is_stale = True
                file_ctx.last_modified = last_modified
                file_ctx.content_hash = content_hash
                file_ctx.size = size
                logger.debug(f"📄 File {file_path} marked as stale")
        else:
            context.file_contexts[file_path] = FileContext(
                path=file_path,
                last_read=time.time(),
                last_modified=last_modified,
                size=size,
                content_hash=content_hash,
                access_count=1
            )

        logger.debug(f"📁 Tracked file access: {file_path}")

    def track_tool_call(self, session_id: str, tool_name: str, parameters: Dict[str, Any],
                       result: Optional[Dict[str, Any]] = None, duration_ms: Optional[float] = None) -> None:
        """Track tool call for pattern analysis."""
        context = self.get_context(session_id)
        if not context:
            return

        tool_call = ToolCall(
            tool_name=tool_name,
            parameters=parameters.copy(),
            timestamp=time.time(),
            result=result,
            duration_ms=duration_ms
        )

        context.tool_calls.append(tool_call)

        # Update tool call count
        context.tool_call_count[tool_name] = context.tool_call_count.get(tool_name, 0) + 1

        logger.debug(f"🔧 Tracked tool call: {tool_name}")

    def get_stale_files(self, session_id: str) -> List[str]:
        """Get list of files that may be stale."""
        context = self.get_context(session_id)
        if not context:
            return []

        return [path for path, file_ctx in context.file_contexts.items() if file_ctx.is_stale]

    def get_frequently_accessed_files(self, session_id: str, limit: int = 10) -> List[str]:
        """Get most frequently accessed files."""
        context = self.get_context(session_id)
        if not context:
            return []

        sorted_files = sorted(
            context.file_contexts.items(),
            key=lambda x: x[1].access_count,
            reverse=True
        )

        return [path for path, _ in sorted_files[:limit]]

    def get_recent_tool_calls(self, session_id: str, limit: int = 10) -> List[ToolCall]:
        """Get recent tool calls."""
        context = self.get_context(session_id)
        if not context:
            return []

        return context.tool_calls[-limit:]

    def set_current_task(self, session_id: str, task: str) -> None:
        """Set current task for context."""
        context = self.get_context(session_id)
        if context:
            context.current_task = task
            logger.debug(f"📋 Set current task: {task}")

    def update_task_progress(self, session_id: str, progress_data: Dict[str, Any]) -> None:
        """Update task progress."""
        context = self.get_context(session_id)
        if context:
            context.task_progress.update(progress_data)

    def set_variable(self, session_id: str, name: str, value: Any) -> None:
        """Set context variable."""
        context = self.get_context(session_id)
        if context:
            context.variables[name] = value

    def get_variable(self, session_id: str, name: str, default: Any = None) -> Any:
        """Get context variable."""
        context = self.get_context(session_id)
        if context:
            return context.variables.get(name, default)
        return default

    def estimate_context_size(self, session_id: str) -> Dict[str, Any]:
        """Estimate context size for memory management."""
        context = self.get_context(session_id)
        if not context:
            return {}

        # Estimate token usage
        file_tokens = sum(file_ctx.size // 4 for file_ctx in context.file_contexts.values())  # Rough estimate
        tool_tokens = len(context.tool_calls) * 50  # Rough estimate per tool call

        total_tokens = file_tokens + tool_tokens
        context.token_count = total_tokens
        context.context_window_used = total_tokens / context.max_tokens

        return {
            "total_tokens": total_tokens,
            "file_tokens": file_tokens,
            "tool_tokens": tool_tokens,
            "context_window_used": context.context_window_used,
            "files_tracked": len(context.file_contexts),
            "tool_calls": len(context.tool_calls)
        }

    def optimize_context(self, session_id: str) -> Dict[str, Any]:
        """Optimize context memory usage."""
        context = self.get_context(session_id)
        if not context:
            return {}

        optimizations = {
            "files_removed": 0,
            "tool_calls_removed": 0,
            "tokens_saved": 0
        }

        # Remove old, infrequently accessed files
        cutoff_time = time.time() - 3600  # 1 hour ago
        files_to_remove = []

        for path, file_ctx in context.file_contexts.items():
            if file_ctx.last_read < cutoff_time and file_ctx.access_count < 2:
                files_to_remove.append(path)

        for path in files_to_remove:
            del context.file_contexts[path]
            optimizations["files_removed"] += 1

        # Trim old tool calls
        if len(context.tool_calls) > 100:
            removed_count = len(context.tool_calls) - 100
            context.tool_calls = context.tool_calls[-100:]
            optimizations["tool_calls_removed"] = removed_count

        # Recalculate context size
        size_info = self.estimate_context_size(session_id)
        optimizations["tokens_saved"] = max(0, size_info.get("total_tokens", 0))

        logger.debug(f"🧹 Optimized context for session {session_id}: {optimizations}")
        return optimizations

    def _cleanup_old_contexts(self, max_age_hours: int = 24) -> None:
        """Clean up old contexts."""
        cutoff_time = time.time() - (max_age_hours * 3600)
        contexts_to_remove = []

        for session_id, context in self.contexts.items():
            if context.last_activity < cutoff_time:
                contexts_to_remove.append(session_id)

        for session_id in contexts_to_remove:
            del self.contexts[session_id]

        if contexts_to_remove:
            logger.info(f"🧹 Cleaned up {len(contexts_to_remove)} old contexts")

    def remove_context(self, session_id: str) -> None:
        """Remove context for session."""
        if session_id in self.contexts:
            del self.contexts[session_id]
            logger.debug(f"🗑️ Removed context for session {session_id}")

    def get_context_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary of conversation context."""
        context = self.get_context(session_id)
        if not context:
            return {}

        return {
            "session_id": session_id,
            "working_directory": context.working_directory,
            "current_task": context.current_task,
            "files_tracked": len(context.file_contexts),
            "stale_files": len(self.get_stale_files(session_id)),
            "tool_calls": len(context.tool_calls),
            "context_window_used": context.context_window_used,
            "created_at": context.created_at,
            "last_activity": context.last_activity
        }


# Global context manager instance
_context_manager = ContextManager()


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    return _context_manager