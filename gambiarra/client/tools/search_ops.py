"""
Advanced search and analysis tools for Gambiarra.
"""

import asyncio
import logging
import os
import re
import subprocess
from typing import Dict, Any, Optional, List, Tuple
from .base import FileOperationTool, ToolResult

logger = logging.getLogger(__name__)


class CodebaseSearchTool(FileOperationTool):
    """Tool for semantic codebase search using various search strategies."""

    @property
    def name(self) -> str:
        return "codebase_search"

    @property
    def risk_level(self) -> str:
        return "low"

    def _is_code_file(self, file_path: str, file_types: Optional[List[str]] = None) -> bool:
        """Check if a file is a code file based on extension."""
        if file_types:
            return any(file_path.endswith(ext) for ext in file_types)

        code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
            '.sql', '.html', '.css', '.scss', '.sass', '.less', '.vue',
            '.yaml', '.yml', '.json', '.xml', '.md', '.sh', '.bash'
        }
        return any(file_path.endswith(ext) for ext in code_extensions)

    def _text_search(self, query: str, file_path: str, max_context_lines: int = 3) -> List[Dict[str, Any]]:
        """Perform text-based search in a file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            results = []
            for i, line in enumerate(lines):
                if query.lower() in line.lower():
                    # Get context lines
                    start_line = max(0, i - max_context_lines)
                    end_line = min(len(lines), i + max_context_lines + 1)

                    context_lines = [line.rstrip() for line in lines[start_line:end_line]]

                    results.append({
                        'line_number': i + 1,
                        'start_line': start_line + 1,
                        'end_line': end_line,
                        'match_line': line.rstrip(),
                        'context': context_lines,
                        'score': 1.0  # Simple scoring for text search
                    })

            return results

        except Exception as e:
            logger.warning(f"Error searching file {file_path}: {e}")
            return []

    def _regex_search(self, pattern: str, file_path: str, max_context_lines: int = 3) -> List[Dict[str, Any]]:
        """Perform regex-based search in a file."""
        try:
            regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)

            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()

            results = []
            for match in regex.finditer(content):
                # Find line number
                line_start = content.rfind('\n', 0, match.start()) + 1
                line_num = content[:match.start()].count('\n') + 1

                # Get context
                start_line = max(0, line_num - max_context_lines - 1)
                end_line = min(len(lines), line_num + max_context_lines)

                context_lines = lines[start_line:end_line]

                results.append({
                    'line_number': line_num,
                    'start_line': start_line + 1,
                    'end_line': end_line,
                    'match_text': match.group(),
                    'match_line': lines[line_num - 1] if line_num <= len(lines) else '',
                    'context': context_lines,
                    'score': 1.0
                })

            return results

        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            return []
        except Exception as e:
            logger.warning(f"Error regex searching file {file_path}: {e}")
            return []

    def _semantic_search(self, query: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Perform semantic search (placeholder for vector search implementation).
        This would integrate with vector databases like Qdrant, ChromaDB, etc.
        """
        # Placeholder implementation - falls back to enhanced text search
        # In a real implementation, this would:
        # 1. Split file into semantic chunks (functions, classes, etc.)
        # 2. Embed chunks using language models
        # 3. Perform vector similarity search
        # 4. Return ranked results

        # For now, do enhanced text search with better scoring
        results = self._text_search(query, file_path)

        # Enhanced scoring based on semantic hints
        for result in results:
            line = result['match_line'].lower()
            score = result['score']

            # Boost score for function/class definitions
            if 'def ' in line or 'class ' in line or 'function ' in line:
                score += 0.5

            # Boost score for comments/docstrings
            if line.strip().startswith('#') or '"""' in line or "'''" in line:
                score += 0.3

            # Boost score for exact word matches
            if query.lower() in line.split():
                score += 0.2

            result['score'] = min(score, 2.0)  # Cap at 2.0

        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    async def execute(self, query: str, path: Optional[str] = None,
                     file_types: Optional[List[str]] = None,
                     max_results: int = 20, search_type: str = "auto", **kwargs) -> ToolResult:
        """
        Search through the codebase for relevant code snippets.

        Args:
            query: Search query
            path: Optional directory to limit search scope
            file_types: Optional file extensions to include
            max_results: Maximum number of results
            search_type: Type of search to perform

        Returns:
            ToolResult with search results
        """
        try:
            # Determine search root
            if path:
                search_root = self.get_absolute_path(path)
                if not os.path.exists(search_root):
                    return ToolResult(
                        success=False,
                        error=f"Search path does not exist: {path}"
                    )
            else:
                search_root = self.working_directory

            # Determine search strategy
            if search_type == "auto":
                # Auto-detect based on query patterns
                if re.search(r'[.*+?^${}()|[\]\\]', query):
                    actual_search_type = "regex"
                else:
                    actual_search_type = "semantic"
            else:
                actual_search_type = search_type

            # Collect files to search
            files_to_search = []
            for root, dirs, files in os.walk(search_root):
                # Skip hidden directories and common non-source directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', 'build', 'dist'}]

                for file in files:
                    file_path = os.path.join(root, file)
                    if self._is_code_file(file_path, file_types):
                        files_to_search.append(file_path)

            # Perform search
            all_results = []
            for file_path in files_to_search:
                try:
                    if actual_search_type == "semantic":
                        file_results = self._semantic_search(query, file_path)
                    elif actual_search_type == "regex":
                        file_results = self._regex_search(query, file_path)
                    else:  # text
                        file_results = self._text_search(query, file_path)

                    # Add file path to results
                    for result in file_results:
                        result['file_path'] = os.path.relpath(file_path, self.working_directory)
                        all_results.append(result)

                except Exception as e:
                    logger.warning(f"Error searching file {file_path}: {e}")
                    continue

            # Sort and limit results
            all_results.sort(key=lambda x: x['score'], reverse=True)
            limited_results = all_results[:max_results]

            # Format results summary
            if not limited_results:
                message = f"No results found for query: '{query}'"
            else:
                unique_files = len(set(r['file_path'] for r in limited_results))
                message = f"Found {len(limited_results)} matches in {unique_files} files for query: '{query}'"

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "search_type": actual_search_type,
                    "total_results": len(limited_results),
                    "files_searched": len(files_to_search),
                    "results": limited_results
                },
                message=message
            )

        except Exception as e:
            logger.error(f"Error in codebase search: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to search codebase: {str(e)}"
            )


class UpdateTodoListTool(FileOperationTool):
    """Tool for managing TODO lists in projects."""

    @property
    def name(self) -> str:
        return "update_todo_list"

    @property
    def risk_level(self) -> str:
        return "low"

    def __init__(self):
        super().__init__()
        self.todo_list = []
        self.next_id = 1

    def _generate_todo_id(self) -> str:
        """Generate a unique TODO ID."""
        todo_id = f"todo_{self.next_id:04d}"
        self.next_id += 1
        return todo_id

    def _find_todo(self, todo_id: str) -> Optional[Dict[str, Any]]:
        """Find a TODO item by ID."""
        for todo in self.todo_list:
            if todo['id'] == todo_id:
                return todo
        return None

    async def execute(self, action: str, todo_id: Optional[str] = None,
                     description: Optional[str] = None, priority: str = "medium",
                     file_path: Optional[str] = None, line_number: Optional[int] = None,
                     **kwargs) -> ToolResult:
        """
        Manage TODO list items.

        Args:
            action: Action to perform
            todo_id: ID of TODO item (for update/remove/complete)
            description: TODO description (for add/update)
            priority: Priority level
            file_path: Optional associated file
            line_number: Optional line number

        Returns:
            ToolResult with TODO list operation status
        """
        try:
            if action == "add":
                if not description:
                    return ToolResult(
                        success=False,
                        error="Description required for adding TODO"
                    )

                new_todo = {
                    "id": self._generate_todo_id(),
                    "description": description,
                    "priority": priority,
                    "status": "pending",
                    "created_at": asyncio.get_event_loop().time()
                }

                if file_path:
                    new_todo["file_path"] = file_path
                if line_number:
                    new_todo["line_number"] = line_number

                self.todo_list.append(new_todo)

                return ToolResult(
                    success=True,
                    data={"todo": new_todo, "total_todos": len(self.todo_list)},
                    message=f"Added TODO: {description}"
                )

            elif action == "update":
                if not todo_id:
                    return ToolResult(
                        success=False,
                        error="TODO ID required for update"
                    )

                todo = self._find_todo(todo_id)
                if not todo:
                    return ToolResult(
                        success=False,
                        error=f"TODO not found: {todo_id}"
                    )

                if description:
                    todo["description"] = description
                if priority:
                    todo["priority"] = priority
                todo["updated_at"] = asyncio.get_event_loop().time()

                return ToolResult(
                    success=True,
                    data={"todo": todo},
                    message=f"Updated TODO: {todo_id}"
                )

            elif action == "complete":
                if not todo_id:
                    return ToolResult(
                        success=False,
                        error="TODO ID required for completion"
                    )

                todo = self._find_todo(todo_id)
                if not todo:
                    return ToolResult(
                        success=False,
                        error=f"TODO not found: {todo_id}"
                    )

                todo["status"] = "completed"
                todo["completed_at"] = asyncio.get_event_loop().time()

                return ToolResult(
                    success=True,
                    data={"todo": todo},
                    message=f"Completed TODO: {todo['description']}"
                )

            elif action == "remove":
                if not todo_id:
                    return ToolResult(
                        success=False,
                        error="TODO ID required for removal"
                    )

                todo = self._find_todo(todo_id)
                if not todo:
                    return ToolResult(
                        success=False,
                        error=f"TODO not found: {todo_id}"
                    )

                self.todo_list.remove(todo)

                return ToolResult(
                    success=True,
                    data={"removed_todo": todo, "total_todos": len(self.todo_list)},
                    message=f"Removed TODO: {todo['description']}"
                )

            elif action == "list":
                # Filter and sort TODOs
                active_todos = [todo for todo in self.todo_list if todo["status"] != "completed"]
                completed_todos = [todo for todo in self.todo_list if todo["status"] == "completed"]

                # Sort by priority and creation time
                priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                active_todos.sort(key=lambda x: (priority_order.get(x["priority"], 2), x["created_at"]))

                return ToolResult(
                    success=True,
                    data={
                        "active_todos": active_todos,
                        "completed_todos": completed_todos,
                        "total_active": len(active_todos),
                        "total_completed": len(completed_todos)
                    },
                    message=f"TODO list: {len(active_todos)} active, {len(completed_todos)} completed"
                )

            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Error managing TODO list: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to manage TODO: {str(e)}"
            )