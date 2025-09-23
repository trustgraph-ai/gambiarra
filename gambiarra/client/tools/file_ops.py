"""
File operation tools for Gambiarra client.
Implements secure file system access with XML-based tool calling.
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import aiofiles
import fnmatch
import re

from gambiarra.client.tools.base import FileOperationTool, ToolResult
from gambiarra.client.security.path_validator import SecurityError


class ReadFileTool(FileOperationTool):
    """Read file contents with optional line ranges."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Read file contents."""
        self.validate_parameters(parameters, ["path"], ["start_line", "end_line", "line_range"])

        path = parameters["path"]
        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")
        line_range = parameters.get("line_range")

        # Support line_range format [start, end]
        if line_range:
            if isinstance(line_range, list) and len(line_range) == 2:
                start_line, end_line = line_range
            else:
                return ToolResult.create_error(
                    "INVALID_LINE_RANGE_FORMAT",
                    "line_range must be a list of [start_line, end_line]",
                    {"provided_line_range": line_range}
                )

        try:
            # Validate path through security manager (this calls PathValidator)
            validated_path = self.validate_path(path)

            # Check if file exists
            if not os.path.exists(validated_path):
                return ToolResult.create_error(
                    "FILE_NOT_FOUND",
                    f"File '{path}' does not exist",
                    {"attempted_path": path, "validated_path": validated_path}
                )

            # Read file content using validated path
            async with aiofiles.open(validated_path, 'r', encoding='utf-8') as file:
                content = await file.read()

            lines = content.split('\n')

            # Handle trailing newline in line count calculation
            actual_line_count = len(lines)
            if content.endswith('\n') and lines and lines[-1] == '':
                actual_line_count -= 1

            # Apply line range if specified
            if start_line is not None or end_line is not None:
                # Validate line parameters
                if start_line is not None and start_line < 1:
                    return ToolResult.create_error(
                        "INVALID_LINE_RANGE",
                        f"start_line must be >= 1, got {start_line}",
                        {"total_lines": len(lines)}
                    )

                if start_line is None:
                    start_line = 1
                if end_line is None:
                    end_line = len(lines)

                if end_line < start_line or start_line > actual_line_count:
                    return ToolResult.create_error(
                        "INVALID_LINE_RANGE",
                        f"Invalid line range: {start_line}-{end_line}",
                        {"total_lines": actual_line_count, "start_line": start_line, "end_line": end_line}
                    )

                # Convert to 0-based indexing for slicing
                result_content = '\n'.join(lines[start_line-1:end_line])
                read_lines = f"{start_line}-{end_line}"
            else:
                result_content = content
                read_lines = "all"

            # Track file read in context tracker
            self.security_manager.track_file_read(validated_path, result_content)

            return ToolResult.success(
                data=result_content,
                metadata={
                    "file_size": len(content),
                    "line_count": actual_line_count,
                    "read_lines": read_lines,
                    "encoding": "utf-8"
                }
            )

        except SecurityError as e:
            return ToolResult.create_error(
                "SECURITY_ERROR",
                str(e),
                {"path": path, "security_details": e.details}
            )
        except UnicodeDecodeError:
            return ToolResult.create_error(
                "ENCODING_ERROR",
                "File contains non-UTF-8 content",
                {"path": path}
            )
        except PermissionError:
            return ToolResult.create_error(
                "PERMISSION_DENIED",
                f"Permission denied reading file '{path}'",
                {"path": path}
            )
        except Exception as e:
            return ToolResult.create_error(
                "FILE_READ_ERROR",
                str(e),
                {"path": path}
            )


class WriteToFileTool(FileOperationTool):
    """Write content to file with backup support."""

    @property
    def name(self) -> str:
        return "write_to_file"

    @property
    def risk_level(self) -> str:
        return "high"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Write content to file."""
        self.validate_parameters(parameters, ["path", "content"], ["line_count"])

        path = parameters["path"]
        content = parameters["content"]
        expected_line_count = parameters.get("line_count")

        try:
            file_path = Path(path)
            backup_created = False

            # Create backup if file exists
            if file_path.exists():
                backup_path = f"{path}.backup"
                shutil.copy2(path, backup_path)
                backup_created = True

            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            async with aiofiles.open(path, 'w', encoding='utf-8') as file:
                await file.write(content)

            # Verify line count if provided
            if expected_line_count:
                # Convert to int if it's a string
                try:
                    expected_line_count = int(expected_line_count)
                except (ValueError, TypeError):
                    expected_line_count = None

            if expected_line_count:
                # Count lines more accurately - handle empty content and trailing newlines
                if not content:
                    actual_line_count = 0
                else:
                    # Split by newlines, but don't count empty string at end if content ends with newline
                    lines = content.split('\n')
                    # If content ends with newline, split creates empty string at end - remove it
                    if content.endswith('\n') and lines and lines[-1] == '':
                        lines = lines[:-1]
                    actual_line_count = len(lines)

                if actual_line_count != expected_line_count:
                    return ToolResult.create_error(
                        "LINE_COUNT_MISMATCH",
                        f"Expected {expected_line_count} lines, got {actual_line_count}",
                        {
                            "expected": expected_line_count,
                            "actual": actual_line_count
                        }
                    )

            # Track file write in context tracker
            if hasattr(self.security_manager, 'track_file_write'):
                self.security_manager.track_file_write(path, content)

            operation = "file_created" if not backup_created else "file_updated"

            return ToolResult.success(
                metadata={
                    "operation": operation,
                    "path": path,
                    "bytes_written": len(content.encode('utf-8')),
                    "line_count": actual_line_count,
                    "backup_created": backup_created
                }
            )

        except PermissionError:
            return ToolResult.create_error(
                "PERMISSION_DENIED",
                f"Permission denied writing to '{path}'",
                {"path": path}
            )
        except Exception as e:
            return ToolResult.create_error(
                "FILE_WRITE_ERROR",
                str(e),
                {"path": path}
            )


class SearchFilesTool(FileOperationTool):
    """Search for patterns across multiple files."""

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Search files for regex pattern."""
        self.validate_parameters(parameters, ["path", "regex"], ["file_pattern"])

        search_path = parameters["path"]
        regex_pattern = parameters["regex"]
        file_pattern = parameters.get("file_pattern", "*")

        try:
            # Compile regex
            regex = re.compile(regex_pattern, re.IGNORECASE | re.MULTILINE)

            # Find matching files
            matches = []
            files_searched = 0
            total_matches = 0

            search_dir = Path(search_path)
            if not search_dir.exists():
                return ToolResult.create_error(
                    "PATH_NOT_FOUND",
                    f"Search path '{search_path}' does not exist",
                    {"path": search_path}
                )

            # Walk through directory
            for file_path in search_dir.rglob(file_pattern):
                if not file_path.is_file():
                    continue

                # Skip binary files
                if self._is_binary_file(file_path):
                    continue

                files_searched += 1

                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
                        content = await file.read()

                    lines = content.split('\n')
                    file_matches = []

                    for line_num, line in enumerate(lines, 1):
                        match = regex.search(line)
                        if match:
                            file_matches.append({
                                "line": line_num,
                                "content": line.strip(),
                                "match": match.group(0)
                            })

                    if file_matches:
                        relative_path = str(file_path.relative_to(search_dir))
                        matches.append({
                            "file": relative_path,
                            "matches": file_matches
                        })
                        total_matches += len(file_matches)

                except (UnicodeDecodeError, PermissionError):
                    # Skip files we can't read
                    continue

            return ToolResult.success(
                data=matches,
                metadata={
                    "files_searched": files_searched,
                    "total_matches": total_matches,
                    "pattern": regex_pattern,
                    "file_pattern": file_pattern
                }
            )

        except re.error as e:
            return ToolResult.create_error(
                "INVALID_REGEX",
                f"Invalid regex pattern: {e}",
                {"pattern": regex_pattern}
            )
        except Exception as e:
            return ToolResult.create_error(
                "SEARCH_ERROR",
                str(e),
                {"path": search_path, "pattern": regex_pattern}
            )

    def _is_binary_file(self, file_path: Path) -> bool:
        """Check if file is binary."""
        try:
            with open(file_path, 'rb') as file:
                chunk = file.read(1024)
                return b'\0' in chunk
        except:
            return True


class ListFilesTool(FileOperationTool):
    """List directory contents."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def risk_level(self) -> str:
        return "low"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """List files in directory."""
        self.validate_parameters(parameters, ["path"], ["recursive"])

        path = parameters["path"]
        recursive = parameters.get("recursive", False)

        try:
            dir_path = Path(path)
            if not dir_path.exists():
                return ToolResult.create_error(
                    "PATH_NOT_FOUND",
                    f"Directory '{path}' does not exist",
                    {"path": path}
                )

            if not dir_path.is_dir():
                return ToolResult.create_error(
                    "NOT_A_DIRECTORY",
                    f"Path '{path}' is not a directory",
                    {"path": path}
                )

            files = []
            directories = []

            if recursive:
                # Recursive listing
                for item in dir_path.rglob("*"):
                    relative_path = str(item.relative_to(dir_path))

                    if item.is_file():
                        files.append({
                            "name": relative_path,
                            "size": item.stat().st_size,
                            "modified": item.stat().st_mtime,
                            "type": "file"
                        })
                    elif item.is_dir():
                        directories.append({
                            "name": relative_path,
                            "type": "directory"
                        })
            else:
                # Non-recursive listing
                for item in dir_path.iterdir():
                    if item.is_file():
                        files.append({
                            "name": item.name,
                            "size": item.stat().st_size,
                            "modified": item.stat().st_mtime,
                            "type": "file"
                        })
                    elif item.is_dir():
                        directories.append({
                            "name": item.name,
                            "type": "directory"
                        })

            # Sort results
            files.sort(key=lambda x: x["name"])
            directories.sort(key=lambda x: x["name"])

            return ToolResult.success(
                data={
                    "files": files,
                    "directories": directories
                },
                metadata={
                    "path": path,
                    "file_count": len(files),
                    "directory_count": len(directories),
                    "recursive": recursive
                }
            )

        except PermissionError:
            return ToolResult.create_error(
                "PERMISSION_DENIED",
                f"Permission denied accessing directory '{path}'",
                {"path": path}
            )
        except Exception as e:
            return ToolResult.create_error(
                "LIST_ERROR",
                str(e),
                {"path": path}
            )


class InsertContentTool(FileOperationTool):
    """Insert content at specific line in file."""

    @property
    def name(self) -> str:
        return "insert_content"

    @property
    def risk_level(self) -> str:
        return "medium"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Insert content at specified line."""
        self.validate_parameters(parameters, ["path", "line_number", "content"])

        path = parameters["path"]
        line_number = parameters["line_number"]
        content = parameters["content"]

        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult.create_error(
                    "FILE_NOT_FOUND",
                    f"File '{path}' does not exist",
                    {"path": path}
                )

            # Read current content
            async with aiofiles.open(path, 'r', encoding='utf-8') as file:
                lines = (await file.read()).split('\n')

            # Validate line number
            if line_number < 1 or line_number > len(lines) + 1:
                return ToolResult.create_error(
                    "INVALID_LINE_NUMBER",
                    f"Line number {line_number} is out of range",
                    {"total_lines": len(lines), "requested_line": line_number}
                )

            # Create backup
            backup_path = f"{path}.backup"
            shutil.copy2(path, backup_path)

            # Insert content
            lines.insert(line_number - 1, content)
            new_content = '\n'.join(lines)

            # Write back
            async with aiofiles.open(path, 'w', encoding='utf-8') as file:
                await file.write(new_content)

            # Track file write in context tracker
            if hasattr(self.security_manager, 'track_file_write'):
                self.security_manager.track_file_write(path, new_content)

            return ToolResult.success(
                metadata={
                    "operation": "content_inserted",
                    "path": path,
                    "line_number": line_number,
                    "lines_added": 1,
                    "new_line_count": len(lines),
                    "backup_created": True
                }
            )

        except Exception as e:
            return ToolResult.create_error(
                "INSERT_ERROR",
                str(e),
                {"path": path, "line_number": line_number}
            )


class SearchAndReplaceTool(FileOperationTool):
    """Search and replace text in file."""

    @property
    def name(self) -> str:
        return "search_and_replace"

    @property
    def risk_level(self) -> str:
        return "medium"

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Search and replace text in file."""
        self.validate_parameters(parameters, ["path", "search", "replace"])

        path = parameters["path"]
        search_text = parameters["search"]
        replace_text = parameters["replace"]

        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult.create_error(
                    "FILE_NOT_FOUND",
                    f"File '{path}' does not exist",
                    {"path": path}
                )

            # Read current content
            async with aiofiles.open(path, 'r', encoding='utf-8') as file:
                original_content = await file.read()

            # Perform replacement
            new_content = original_content.replace(search_text, replace_text)

            # Count replacements
            replacements_made = original_content.count(search_text)

            if replacements_made == 0:
                return ToolResult.create_error(
                    "SEARCH_TEXT_NOT_FOUND",
                    f"Search text not found in file: '{search_text}'",
                    {"search_text": search_text, "path": path}
                )

            # Create backup
            backup_path = f"{path}.backup"
            shutil.copy2(path, backup_path)

            # Write new content
            async with aiofiles.open(path, 'w', encoding='utf-8') as file:
                await file.write(new_content)

            # Track file write in context tracker
            if hasattr(self.security_manager, 'track_file_write'):
                self.security_manager.track_file_write(path, new_content)

            return ToolResult.success(
                metadata={
                    "operation": "search_and_replace",
                    "path": path,
                    "replacements_made": replacements_made,
                    "search_text": search_text,
                    "replace_text": replace_text,
                    "backup_created": True
                }
            )

        except Exception as e:
            return ToolResult.create_error(
                "REPLACE_ERROR",
                str(e),
                {"path": path, "search": search_text}
            )