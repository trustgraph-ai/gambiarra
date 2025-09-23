"""
Enhanced session context management.
Provides rich conversation context tracking and memory management.
"""

import logging
import time
import re
from typing import Dict, List, Any, Optional, Set, Tuple
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

    # Enhanced dependency tracking
    dependencies: Set[str] = field(default_factory=set)  # Files this file depends on
    dependents: Set[str] = field(default_factory=set)    # Files that depend on this file
    language: Optional[str] = None
    file_type: Optional[str] = None
    last_analyzed: Optional[float] = None


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


class FileDependencyAnalyzer:
    """Analyzes file dependencies to understand project structure."""

    # Language-specific import patterns
    IMPORT_PATTERNS = {
        "python": [
            r"^from\s+([^\s]+)\s+import",
            r"^import\s+([^\s,]+)",
            r"^from\s+([^\s]+)\s+import\s+[^#]*",
        ],
        "javascript": [
            r"^import.*from\s+['\"]([^'\"]+)['\"]",
            r"^const.*=\s*require\(['\"]([^'\"]+)['\"]\)",
            r"^import\s+['\"]([^'\"]+)['\"]",
        ],
        "typescript": [
            r"^import.*from\s+['\"]([^'\"]+)['\"]",
            r"^import\s+['\"]([^'\"]+)['\"]",
            r"^const.*=\s*require\(['\"]([^'\"]+)['\"]\)",
        ],
        "java": [
            r"^import\s+([^;]+);",
            r"^package\s+([^;]+);",
        ],
        "go": [
            r"^import\s+\"([^\"]+)\"",
            r"^\s*\"([^\"]+)\"",  # Inside import blocks
        ]
    }

    # File extension to language mapping
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp"
    }

    @classmethod
    def detect_language(cls, file_path: str) -> Optional[str]:
        """Detect programming language from file extension."""
        path_obj = Path(file_path)
        return cls.LANGUAGE_MAP.get(path_obj.suffix.lower())

    @classmethod
    def analyze_dependencies(cls, file_path: str, content: str) -> Set[str]:
        """Analyze file dependencies from content."""
        language = cls.detect_language(file_path)
        if not language or language not in cls.IMPORT_PATTERNS:
            return set()

        dependencies = set()
        patterns = cls.IMPORT_PATTERNS[language]

        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue

            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    import_path = match.group(1)
                    # Resolve relative imports to actual file paths
                    resolved_path = cls._resolve_import_path(file_path, import_path, language)
                    if resolved_path:
                        dependencies.add(resolved_path)

        return dependencies

    @classmethod
    def _resolve_import_path(cls, current_file: str, import_path: str, language: str) -> Optional[str]:
        """Resolve import path to actual file path."""
        current_dir = Path(current_file).parent

        if language == "python":
            # Handle relative imports
            if import_path.startswith('.'):
                # Relative import
                parts = import_path.split('.')
                relative_path = current_dir
                for part in parts:
                    if part:  # Skip empty parts from leading dots
                        relative_path = relative_path / part

                # Try .py extension
                py_file = relative_path.with_suffix('.py')
                if py_file.exists():
                    return str(py_file)

                # Try __init__.py in directory
                init_file = relative_path / "__init__.py"
                if init_file.exists():
                    return str(init_file)
            else:
                # Absolute import - convert dots to path
                parts = import_path.split('.')
                # Try to find in current project
                potential_path = current_dir
                for part in parts:
                    potential_path = potential_path / part

                py_file = potential_path.with_suffix('.py')
                if py_file.exists():
                    return str(py_file)

        elif language in ["javascript", "typescript"]:
            # Handle relative imports
            if import_path.startswith('./') or import_path.startswith('../'):
                resolved = (current_dir / import_path).resolve()

                # Try different extensions
                for ext in ['.js', '.jsx', '.ts', '.tsx']:
                    file_with_ext = resolved.with_suffix(ext)
                    if file_with_ext.exists():
                        return str(file_with_ext)

                # Try index files
                if resolved.is_dir():
                    for ext in ['.js', '.jsx', '.ts', '.tsx']:
                        index_file = resolved / f"index{ext}"
                        if index_file.exists():
                            return str(index_file)

        return None

    @classmethod
    def get_file_type(cls, file_path: str) -> str:
        """Get file type classification."""
        path_obj = Path(file_path)
        name = path_obj.name.lower()
        suffix = path_obj.suffix.lower()

        # Special files
        if name in ['readme.md', 'readme.txt', 'readme']:
            return "documentation"
        elif name in ['package.json', 'requirements.txt', 'cargo.toml', 'pom.xml']:
            return "config"
        elif name.startswith('.'):
            return "config"
        elif suffix in ['.md', '.txt', '.rst']:
            return "documentation"
        elif suffix in ['.json', '.yaml', '.yml', '.toml', '.ini', '.cfg']:
            return "config"
        elif '.test.' in name or '.spec.' in name or name.endswith('_test.py') or name.endswith('_spec.py'):
            return "test"
        elif suffix in ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.c', '.cpp']:
            return "source"
        else:
            return "unknown"


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
        """Track file access for context management with dependency analysis."""
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

        # Detect language and file type
        language = FileDependencyAnalyzer.detect_language(file_path)
        file_type = FileDependencyAnalyzer.get_file_type(file_path)

        # Analyze dependencies
        dependencies = FileDependencyAnalyzer.analyze_dependencies(file_path, content)

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

                # Update dependency analysis
                file_ctx.dependencies = dependencies
                file_ctx.language = language
                file_ctx.file_type = file_type
                file_ctx.last_analyzed = time.time()

                logger.debug(f"📄 File {file_path} updated with {len(dependencies)} dependencies")
        else:
            context.file_contexts[file_path] = FileContext(
                path=file_path,
                last_read=time.time(),
                last_modified=last_modified,
                size=size,
                content_hash=content_hash,
                access_count=1,
                dependencies=dependencies,
                language=language,
                file_type=file_type,
                last_analyzed=time.time()
            )

        # Update bidirectional dependencies
        self._update_dependency_graph(context, file_path, dependencies)

        logger.debug(f"📁 Tracked file access: {file_path} ({file_type}, {len(dependencies)} deps)")

    def _update_dependency_graph(self, context: ConversationContext, file_path: str, dependencies: Set[str]) -> None:
        """Update bidirectional dependency graph."""
        # Clear old dependencies for this file
        for dep_path, file_ctx in context.file_contexts.items():
            if file_path in file_ctx.dependents:
                file_ctx.dependents.remove(file_path)

        # Add new dependencies
        for dep_path in dependencies:
            if dep_path in context.file_contexts:
                context.file_contexts[dep_path].dependents.add(file_path)

    def get_file_dependencies(self, session_id: str, file_path: str, recursive: bool = False) -> Set[str]:
        """Get dependencies of a file."""
        context = self.get_context(session_id)
        if not context or file_path not in context.file_contexts:
            return set()

        file_ctx = context.file_contexts[file_path]
        dependencies = file_ctx.dependencies.copy()

        if recursive:
            # Recursively get dependencies of dependencies
            visited = {file_path}
            to_visit = list(dependencies)

            while to_visit:
                current = to_visit.pop()
                if current in visited or current not in context.file_contexts:
                    continue

                visited.add(current)
                current_deps = context.file_contexts[current].dependencies
                dependencies.update(current_deps)
                to_visit.extend(current_deps - visited)

        return dependencies

    def get_file_dependents(self, session_id: str, file_path: str, recursive: bool = False) -> Set[str]:
        """Get files that depend on this file."""
        context = self.get_context(session_id)
        if not context or file_path not in context.file_contexts:
            return set()

        file_ctx = context.file_contexts[file_path]
        dependents = file_ctx.dependents.copy()

        if recursive:
            # Recursively get dependents of dependents
            visited = {file_path}
            to_visit = list(dependents)

            while to_visit:
                current = to_visit.pop()
                if current in visited or current not in context.file_contexts:
                    continue

                visited.add(current)
                current_deps = context.file_contexts[current].dependents
                dependents.update(current_deps)
                to_visit.extend(current_deps - visited)

        return dependents

    def get_files_by_type(self, session_id: str, file_type: str) -> List[str]:
        """Get files of a specific type."""
        context = self.get_context(session_id)
        if not context:
            return []

        return [
            path for path, file_ctx in context.file_contexts.items()
            if file_ctx.file_type == file_type
        ]

    def get_files_by_language(self, session_id: str, language: str) -> List[str]:
        """Get files of a specific programming language."""
        context = self.get_context(session_id)
        if not context:
            return []

        return [
            path for path, file_ctx in context.file_contexts.items()
            if file_ctx.language == language
        ]

    def find_related_files(self, session_id: str, file_path: str) -> Dict[str, List[str]]:
        """Find files related to the given file."""
        context = self.get_context(session_id)
        if not context or file_path not in context.file_contexts:
            return {}

        file_ctx = context.file_contexts[file_path]

        related = {
            "dependencies": list(file_ctx.dependencies),
            "dependents": list(file_ctx.dependents),
            "same_language": [],
            "same_directory": []
        }

        # Find files in same language
        if file_ctx.language:
            related["same_language"] = [
                path for path, ctx in context.file_contexts.items()
                if ctx.language == file_ctx.language and path != file_path
            ]

        # Find files in same directory
        file_dir = str(Path(file_path).parent)
        related["same_directory"] = [
            path for path in context.file_contexts.keys()
            if str(Path(path).parent) == file_dir and path != file_path
        ]

        return related

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