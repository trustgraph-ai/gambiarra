"""
Diff application and patch management tools for Gambiarra.
"""

import asyncio
import logging
import os
import re
import tempfile
from typing import Dict, Any, Optional, List, Tuple
from .base import FileOperationTool, ToolResult

logger = logging.getLogger(__name__)


class ApplyDiffTool(FileOperationTool):
    """Tool for applying unified diff patches to files."""

    @property
    def name(self) -> str:
        return "apply_diff"

    @property
    def risk_level(self) -> str:
        return "medium"

    def _parse_unified_diff(self, diff_content: str) -> List[Dict[str, Any]]:
        """Parse unified diff into structured format."""
        hunks = []
        lines = diff_content.split('\n')

        current_hunk = None
        for line in lines:
            if line.startswith('@@'):
                # Extract hunk header info
                match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) else 1

                    if current_hunk:
                        hunks.append(current_hunk)

                    current_hunk = {
                        'old_start': old_start,
                        'old_count': old_count,
                        'new_start': new_start,
                        'new_count': new_count,
                        'lines': []
                    }
            elif current_hunk is not None:
                if line.startswith(' ') or line.startswith('+') or line.startswith('-'):
                    current_hunk['lines'].append(line)

        if current_hunk:
            hunks.append(current_hunk)

        return hunks

    def _apply_hunk(self, file_lines: List[str], hunk: Dict[str, Any]) -> Tuple[bool, List[str], str]:
        """Apply a single hunk to file lines."""
        try:
            old_start = hunk['old_start'] - 1  # Convert to 0-based indexing
            new_lines = []
            old_line_idx = 0

            # Build new content for this hunk
            for diff_line in hunk['lines']:
                if diff_line.startswith(' '):
                    # Context line - should match
                    content = diff_line[1:]
                    if old_line_idx + old_start < len(file_lines):
                        if file_lines[old_start + old_line_idx] != content:
                            return False, [], f"Context mismatch at line {old_start + old_line_idx + 1}"
                    new_lines.append(content)
                    old_line_idx += 1
                elif diff_line.startswith('-'):
                    # Deletion - verify it matches and skip
                    content = diff_line[1:]
                    if old_line_idx + old_start < len(file_lines):
                        if file_lines[old_start + old_line_idx] != content:
                            return False, [], f"Deletion mismatch at line {old_start + old_line_idx + 1}"
                    old_line_idx += 1
                elif diff_line.startswith('+'):
                    # Addition
                    content = diff_line[1:]
                    new_lines.append(content)

            # Apply the change
            result_lines = (
                file_lines[:old_start] +
                new_lines +
                file_lines[old_start + hunk['old_count']:]
            )

            return True, result_lines, ""

        except Exception as e:
            return False, [], f"Error applying hunk: {str(e)}"

    async def execute(self, path: str, diff: str, start_line: Optional[int] = None, **kwargs) -> ToolResult:
        """
        Apply a unified diff patch to a file.

        Args:
            path: Path to the file to patch
            diff: Unified diff content
            start_line: Optional starting line for context

        Returns:
            ToolResult with patch application status
        """
        try:
            # Validate file access
            if not await self.validate_file_access(path):
                return ToolResult(
                    success=False,
                    error=f"Access denied to file: {path}"
                )

            file_path = self.get_absolute_path(path)

            # Check if file exists
            if not os.path.exists(file_path):
                return ToolResult(
                    success=False,
                    error=f"File does not exist: {path}"
                )

            # Read original file content
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            original_lines = original_content.splitlines()

            # Parse the diff
            hunks = self._parse_unified_diff(diff)
            if not hunks:
                return ToolResult(
                    success=False,
                    error="No valid hunks found in diff"
                )

            # Apply hunks in reverse order to maintain line numbers
            current_lines = original_lines.copy()
            for hunk in reversed(hunks):
                success, new_lines, error = self._apply_hunk(current_lines, hunk)
                if not success:
                    return ToolResult(
                        success=False,
                        error=f"Failed to apply hunk: {error}",
                        data={"hunk": hunk, "failed_at": error}
                    )
                current_lines = new_lines

            # Write the patched content
            new_content = '\n'.join(current_lines)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # Calculate statistics
            original_line_count = len(original_lines)
            new_line_count = len(current_lines)
            lines_added = max(0, new_line_count - original_line_count)
            lines_removed = max(0, original_line_count - new_line_count)

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "hunks_applied": len(hunks),
                    "lines_added": lines_added,
                    "lines_removed": lines_removed,
                    "original_lines": original_line_count,
                    "new_lines": new_line_count
                },
                message=f"Successfully applied diff to {path} ({len(hunks)} hunks, +{lines_added}/-{lines_removed} lines)"
            )

        except Exception as e:
            logger.error(f"Error applying diff to {path}: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to apply diff: {str(e)}"
            )


class MultiApplyDiffTool(FileOperationTool):
    """Tool for applying multiple diff patches in a single operation."""

    @property
    def name(self) -> str:
        return "multi_apply_diff"

    @property
    def risk_level(self) -> str:
        return "medium"

    def __init__(self):
        super().__init__()
        self.apply_diff_tool = ApplyDiffTool()

    async def execute(self, diffs: List[Dict[str, Any]], continue_on_error: bool = False, **kwargs) -> ToolResult:
        """
        Apply multiple diff patches.

        Args:
            diffs: List of diff operations to apply
            continue_on_error: Whether to continue if one diff fails

        Returns:
            ToolResult with results for all diff applications
        """
        try:
            results = []
            successful_count = 0
            failed_count = 0

            for i, diff_op in enumerate(diffs):
                try:
                    path = diff_op.get('path')
                    diff_content = diff_op.get('diff')
                    start_line = diff_op.get('start_line')

                    if not path or not diff_content:
                        result = ToolResult(
                            success=False,
                            error=f"Missing required parameters in diff operation {i}"
                        )
                    else:
                        result = await self.apply_diff_tool.execute(
                            path=path,
                            diff=diff_content,
                            start_line=start_line
                        )

                    results.append({
                        "index": i,
                        "path": path,
                        "success": result.success,
                        "data": result.data,
                        "error": result.error,
                        "message": result.message
                    })

                    if result.success:
                        successful_count += 1
                    else:
                        failed_count += 1
                        if not continue_on_error:
                            break

                except Exception as e:
                    error_result = {
                        "index": i,
                        "path": diff_op.get('path', 'unknown'),
                        "success": False,
                        "error": f"Exception applying diff: {str(e)}"
                    }
                    results.append(error_result)
                    failed_count += 1

                    if not continue_on_error:
                        break

            # Determine overall success
            overall_success = failed_count == 0 or (continue_on_error and successful_count > 0)

            return ToolResult(
                success=overall_success,
                data={
                    "total_diffs": len(diffs),
                    "successful": successful_count,
                    "failed": failed_count,
                    "results": results
                },
                message=f"Applied {successful_count}/{len(diffs)} diffs successfully"
            )

        except Exception as e:
            logger.error(f"Error in multi diff application: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to apply multiple diffs: {str(e)}"
            )


class EditFileTool(FileOperationTool):
    """Advanced file editing tool with better context awareness."""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def risk_level(self) -> str:
        return "medium"

    async def execute(self, path: str, old_str: str, new_str: str,
                     occurrence: int = 1, context_lines: int = 3, **kwargs) -> ToolResult:
        """
        Edit a file with advanced context awareness.

        Args:
            path: Path to the file to edit
            old_str: String to replace
            new_str: Replacement string
            occurrence: Which occurrence to replace (1-based, 0 for all)
            context_lines: Number of context lines to show

        Returns:
            ToolResult with edit status and context information
        """
        try:
            # Validate file access
            if not await self.validate_file_access(path):
                return ToolResult(
                    success=False,
                    error=f"Access denied to file: {path}"
                )

            file_path = self.get_absolute_path(path)

            # Check if file exists
            if not os.path.exists(file_path):
                return ToolResult(
                    success=False,
                    error=f"File does not exist: {path}"
                )

            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find occurrences
            occurrences = []
            start = 0
            while True:
                pos = content.find(old_str, start)
                if pos == -1:
                    break
                occurrences.append(pos)
                start = pos + 1

            if not occurrences:
                return ToolResult(
                    success=False,
                    error=f"String not found in file: {repr(old_str)}"
                )

            # Determine which occurrences to replace
            if occurrence == 0:
                # Replace all occurrences
                replace_positions = occurrences
            elif 1 <= occurrence <= len(occurrences):
                # Replace specific occurrence
                replace_positions = [occurrences[occurrence - 1]]
            else:
                return ToolResult(
                    success=False,
                    error=f"Occurrence {occurrence} not found (file has {len(occurrences)} occurrences)"
                )

            # Apply replacements (in reverse order to maintain positions)
            new_content = content
            for pos in reversed(replace_positions):
                new_content = new_content[:pos] + new_str + new_content[pos + len(old_str):]

            # Write the modified content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # Generate context information
            lines = content.splitlines()
            context_info = []

            for pos in replace_positions:
                # Find line number for this position
                line_num = content[:pos].count('\n') + 1

                # Get context lines
                start_line = max(1, line_num - context_lines)
                end_line = min(len(lines), line_num + context_lines)

                context_info.append({
                    "position": pos,
                    "line_number": line_num,
                    "context_start": start_line,
                    "context_end": end_line,
                    "context_lines": lines[start_line-1:end_line]
                })

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "replacements_made": len(replace_positions),
                    "total_occurrences": len(occurrences),
                    "old_length": len(old_str),
                    "new_length": len(new_str),
                    "context": context_info
                },
                message=f"Successfully edited {path} ({len(replace_positions)} replacements)"
            )

        except Exception as e:
            logger.error(f"Error editing file {path}: {e}")
            return ToolResult(
                success=False,
                error=f"Failed to edit file: {str(e)}"
            )