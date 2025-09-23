"""
Tests for client-side file operation tools.
"""

import pytest
from unittest.mock import patch, mock_open, AsyncMock
from gambiarra.client.tools.file_ops import ReadFileTool


@pytest.mark.unit
class TestReadFileTool:
    """Test the read_file tool implementation."""

    def test_read_file_tool_initialization(self, mock_security_manager):
        """Test ReadFileTool initialization."""
        tool = ReadFileTool(mock_security_manager)

        assert tool.name == "read_file"
        assert tool.risk_level == "low"
        assert tool.security_manager == mock_security_manager

    @pytest.mark.asyncio
    async def test_read_existing_file(self, mock_security_manager, temp_workspace):
        """Test reading an existing file."""
        tool = ReadFileTool(mock_security_manager)

        # Mock security manager to return valid path
        test_file = temp_workspace / "main.py"
        mock_security_manager.validate_path.return_value = str(test_file)

        parameters = {"path": "main.py"}

        result = await tool.execute(parameters)

        assert result.status == "success"
        assert result.data == "print('Hello, Gambiarra!')\n"
        assert "file_size" in result.metadata
        assert "line_count" in result.metadata
        assert result.metadata["line_count"] == 1

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, mock_security_manager, temp_workspace):
        """Test reading a non-existent file."""
        tool = ReadFileTool(mock_security_manager)

        # Mock security manager to return path to non-existent file
        nonexistent_path = str(temp_workspace / "nonexistent.py")
        mock_security_manager.validate_path.return_value = nonexistent_path

        parameters = {"path": "nonexistent.py"}

        result = await tool.execute(parameters)

        assert result.status == "error"
        assert result.error is not None
        assert result.error["code"] == "FILE_NOT_FOUND"
        assert "nonexistent.py" in result.error["message"]

    @pytest.mark.asyncio
    async def test_parameter_validation(self, mock_security_manager):
        """Test parameter validation for read_file tool."""
        tool = ReadFileTool(mock_security_manager)

        # Test missing required parameter
        with pytest.raises(ValueError, match="Missing required parameter: path"):
            await tool.execute({})

        # Test with valid parameters
        mock_security_manager.validate_path.return_value = "/safe/path/test.py"

        # Mock file operations to avoid actual file I/O
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value="test content")
        mock_file.__aenter__ = AsyncMock(return_value=mock_file)
        mock_file.__aexit__ = AsyncMock(return_value=None)

        with patch("aiofiles.open", return_value=mock_file):
            with patch("os.path.exists", return_value=True):
                result = await tool.execute({"path": "test.py"})
                assert result.status == "success"

    @pytest.mark.asyncio
    async def test_security_integration(self, mock_security_manager):
        """Test integration with security manager."""
        tool = ReadFileTool(mock_security_manager)

        parameters = {"path": "../dangerous/path.py"}

        # Security manager should be called to validate path
        from gambiarra.client.security.path_validator import SecurityError
        mock_security_manager.validate_path.side_effect = SecurityError("Path traversal detected")

        # Should return security error result instead of raising
        result = await tool.execute(parameters)
        assert result.status == "error"
        assert result.error["code"] == "SECURITY_ERROR"

        # Verify security manager was called
        mock_security_manager.validate_path.assert_called_once_with("../dangerous/path.py")

    @pytest.mark.asyncio
    async def test_file_tracking(self, mock_security_manager, temp_workspace):
        """Test file read tracking for context management."""
        tool = ReadFileTool(mock_security_manager)

        # Create the test file
        test_file = temp_workspace / "tracked.py"
        test_file.write_text("# Tracked file content\nprint('tracking test')\n")
        mock_security_manager.validate_path.return_value = str(test_file)

        parameters = {"path": "tracked.py"}

        result = await tool.execute(parameters)

        # Should track file read for context management
        if hasattr(mock_security_manager, 'track_file_read'):
            mock_security_manager.track_file_read.assert_called_once()

    @pytest.mark.asyncio
    async def test_encoding_error_handling(self, mock_security_manager):
        """Test handling of files with encoding issues."""
        tool = ReadFileTool(mock_security_manager)

        mock_security_manager.validate_path.return_value = "/safe/binary_file.bin"

        # Mock aiofiles to raise UnicodeDecodeError
        with patch("os.path.exists", return_value=True):
            with patch("aiofiles.open") as mock_file:
                mock_file.side_effect = UnicodeDecodeError("utf-8", b"\\x80", 0, 1, "invalid start byte")

                result = await tool.execute({"path": "binary_file.bin"})

                assert result.status == "error"
                assert result.error["code"] == "ENCODING_ERROR"
                assert "non-UTF-8" in result.error["message"]

    @pytest.mark.asyncio
    async def test_line_range_functionality(self, mock_security_manager, temp_workspace):
        """Test reading specific line ranges from files."""
        tool = ReadFileTool(mock_security_manager)

        # Create a multi-line test file
        test_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        test_file = temp_workspace / "multiline.py"
        test_file.write_text(test_content)

        mock_security_manager.validate_path.return_value = str(test_file)

        # Test reading specific line range
        parameters = {"path": "multiline.py", "line_range": [2, 4]}

        result = await tool.execute(parameters)

        assert result.status == "success"
        assert result.data == "Line 2\nLine 3\nLine 4"
        assert result.metadata["read_lines"] == "2-4"

    @pytest.mark.asyncio
    async def test_invalid_line_range(self, mock_security_manager, temp_workspace):
        """Test handling of invalid line ranges."""
        tool = ReadFileTool(mock_security_manager)

        test_file = temp_workspace / "main.py"
        mock_security_manager.validate_path.return_value = str(test_file)

        # Test invalid line range (beyond file length)
        parameters = {"path": "main.py", "line_range": [10, 20]}

        result = await tool.execute(parameters)

        assert result.status == "error"
        assert result.error["code"] == "INVALID_LINE_RANGE"
        assert "total_lines" in result.error["details"]


@pytest.mark.unit
@pytest.mark.integration
class TestToolManagerIntegration:
    """Test tool integration with tool manager."""

    def test_tool_registration(self, mock_security_manager):
        """Test tool registration with tool manager."""
        from gambiarra.client.tools.base import ToolManager

        manager = ToolManager(mock_security_manager)
        tool = ReadFileTool(mock_security_manager)

        manager.register_tool(tool)

        assert "read_file" in manager.list_tools()
        assert manager.get_tool("read_file") is tool

    @pytest.mark.asyncio
    async def test_tool_execution_through_manager(self, mock_security_manager, temp_workspace):
        """Test tool execution through the tool manager."""
        from gambiarra.client.tools.base import ToolManager

        manager = ToolManager(mock_security_manager)
        tool = ReadFileTool(mock_security_manager)
        manager.register_tool(tool)

        # Test execution through manager
        test_file = temp_workspace / "main.py"
        mock_security_manager.validate_path.return_value = str(test_file)

        # Test nested args structure (as received from server)
        nested_params = {
            "args": {
                "file": {
                    "path": "main.py"
                }
            }
        }

        result = await manager.execute_tool("read_file", nested_params)

        assert result.status == "success"
        assert result.data == "print('Hello, Gambiarra!')\n"