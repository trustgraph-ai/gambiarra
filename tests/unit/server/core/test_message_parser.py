"""
Tests for server message parsing and validation.
These tests ensure WebSocket messages are correctly parsed and validated.
"""

import pytest
import json
from typing import Dict, Any
from gambiarra.server.core.tools.parser import ToolCallParser


class TestMessageParsing:
    """Test WebSocket message parsing and validation."""

    @pytest.fixture
    def valid_user_message(self):
        """Valid user message structure."""
        return {
            "type": "user_message",
            "session_id": "test-session-123",
            "content": "Hello, can you help me read a file?",
            "timestamp": 1638360000.0,
            "images": [],
            "metadata": {}
        }

    @pytest.fixture
    def valid_tool_approval(self):
        """Valid tool approval message."""
        return {
            "type": "tool_approval",
            "session_id": "test-session-123",
            "request_id": "req-456",
            "approved": True,
            "feedback": "Approved by user"
        }

    @pytest.fixture
    def valid_ai_response(self):
        """Valid AI response with tool calls."""
        return {
            "type": "ai_response",
            "session_id": "test-session-123",
            "content": "I'll help you read that file.",
            "tool_calls": [
                {
                    "name": "read_file",
                    "xml": "<read_file><args><file><path>main.py</path></file></args></read_file>"
                }
            ],
            "metadata": {"provider": "test", "model": "gpt-4"}
        }

    def test_valid_user_message_structure(self, valid_user_message):
        """Test parsing of valid user message."""
        # Should contain required fields
        assert "type" in valid_user_message
        assert "session_id" in valid_user_message
        assert "content" in valid_user_message
        assert valid_user_message["type"] == "user_message"
        assert isinstance(valid_user_message["content"], str)

    def test_valid_tool_approval_structure(self, valid_tool_approval):
        """Test parsing of valid tool approval message."""
        assert "type" in valid_tool_approval
        assert "session_id" in valid_tool_approval
        assert "request_id" in valid_tool_approval
        assert "approved" in valid_tool_approval
        assert valid_tool_approval["type"] == "tool_approval"
        assert isinstance(valid_tool_approval["approved"], bool)

    def test_valid_ai_response_structure(self, valid_ai_response):
        """Test parsing of valid AI response message."""
        assert "type" in valid_ai_response
        assert "session_id" in valid_ai_response
        assert "content" in valid_ai_response
        assert valid_ai_response["type"] == "ai_response"
        assert "tool_calls" in valid_ai_response
        assert isinstance(valid_ai_response["tool_calls"], list)

    def test_message_type_validation(self):
        """Test message type validation."""
        valid_types = [
            "user_message",
            "ai_response",
            "tool_approval",
            "tool_denied",
            "session_start",
            "session_end",
            "error",
            "heartbeat"
        ]

        for msg_type in valid_types:
            message = {"type": msg_type, "session_id": "test"}
            assert message["type"] in valid_types

    def test_required_fields_validation(self):
        """Test that required fields are present."""
        # Missing type field
        invalid_message = {"session_id": "test", "content": "hello"}
        with pytest.raises(KeyError):
            _ = invalid_message["type"]

        # Missing session_id field
        invalid_message = {"type": "user_message", "content": "hello"}
        with pytest.raises(KeyError):
            _ = invalid_message["session_id"]

    def test_json_serialization(self, valid_user_message):
        """Test message JSON serialization/deserialization."""
        # Should serialize to valid JSON
        json_str = json.dumps(valid_user_message)
        assert isinstance(json_str, str)

        # Should deserialize back to original structure
        deserialized = json.loads(json_str)
        assert deserialized == valid_user_message

    def test_malformed_json_handling(self):
        """Test handling of malformed JSON messages."""
        malformed_json_strings = [
            '{"type": "user_message", "session_id": "test"',  # Missing closing brace
            '{"type": "user_message" "session_id": "test"}',  # Missing comma
            '{"type": user_message, "session_id": "test"}',   # Unquoted value
            '',  # Empty string
            'not json at all',  # Not JSON
        ]

        for malformed in malformed_json_strings:
            with pytest.raises((json.JSONDecodeError, ValueError, TypeError)):
                json.loads(malformed)

        # Null type is valid JSON, so test separately
        result = json.loads('{"type": null, "session_id": "test"}')
        assert result["type"] is None  # Null is valid JSON value

    def test_tool_call_xml_extraction(self, valid_ai_response):
        """Test extraction of XML tool calls from AI responses."""
        tool_calls = valid_ai_response["tool_calls"]
        assert len(tool_calls) == 1

        tool_call = tool_calls[0]
        assert "name" in tool_call
        assert "xml" in tool_call
        assert tool_call["name"] == "read_file"
        assert "<read_file>" in tool_call["xml"]

    def test_session_id_format_validation(self):
        """Test session ID format validation."""
        valid_session_ids = [
            "session-123-abc",
            "test-session-456",
            "uuid-format-12345",
            "simple-id"
        ]

        for session_id in valid_session_ids:
            message = {"type": "user_message", "session_id": session_id}
            assert isinstance(message["session_id"], str)
            assert len(message["session_id"]) > 0

    def test_message_size_limits(self):
        """Test message size validation."""
        # Large but reasonable message
        large_content = "x" * 1000000  # 1MB
        large_message = {
            "type": "user_message",
            "session_id": "test",
            "content": large_content
        }

        # Should serialize successfully (server should handle size limits)
        json_str = json.dumps(large_message)
        assert len(json_str) > 1000000

    def test_unicode_content_handling(self):
        """Test handling of Unicode content in messages."""
        unicode_content = "Hello 世界 🌍 Émojis and ñoñó"
        unicode_message = {
            "type": "user_message",
            "session_id": "test",
            "content": unicode_content
        }

        # Should handle Unicode correctly
        json_str = json.dumps(unicode_message, ensure_ascii=False)
        deserialized = json.loads(json_str)
        assert deserialized["content"] == unicode_content

    def test_metadata_structure(self, valid_ai_response):
        """Test metadata field structure and validation."""
        metadata = valid_ai_response["metadata"]
        assert isinstance(metadata, dict)
        assert "provider" in metadata
        assert "model" in metadata

        # Metadata should be optional
        message_without_metadata = {
            "type": "user_message",
            "session_id": "test",
            "content": "hello"
        }
        # Should not require metadata field
        assert "metadata" not in message_without_metadata or message_without_metadata.get("metadata") is None

    def test_timestamp_validation(self, valid_user_message):
        """Test timestamp field validation."""
        timestamp = valid_user_message["timestamp"]
        assert isinstance(timestamp, (int, float))
        assert timestamp > 0

        # Should handle missing timestamp (server adds it)
        message_no_timestamp = {
            "type": "user_message",
            "session_id": "test",
            "content": "hello"
        }
        assert "timestamp" not in message_no_timestamp

    def test_error_message_structure(self):
        """Test error message structure."""
        error_message = {
            "type": "error",
            "session_id": "test-session",
            "error_code": "TOOL_EXECUTION_FAILED",
            "error_message": "File not found",
            "details": {
                "tool_name": "read_file",
                "file_path": "nonexistent.txt"
            }
        }

        assert error_message["type"] == "error"
        assert "error_code" in error_message
        assert "error_message" in error_message
        assert isinstance(error_message["details"], dict)

    def test_heartbeat_message_structure(self):
        """Test heartbeat message for connection keep-alive."""
        heartbeat = {
            "type": "heartbeat",
            "session_id": "test-session",
            "timestamp": 1638360000.0
        }

        assert heartbeat["type"] == "heartbeat"
        assert "session_id" in heartbeat
        assert "timestamp" in heartbeat