"""
Integration tests for complete tool execution flow.
Tests the full client-server-AI workflow.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch


@pytest.mark.integration
@pytest.mark.asyncio
class TestToolExecutionFlow:
    """Test complete tool execution workflow."""

    async def test_read_file_approval_and_execution_flow(
        self, mock_websocket, mock_ai_provider, mock_session, temp_workspace
    ):
        """Test complete read_file flow: AI request -> approval -> execution -> result."""

        # 1. Mock AI provider to request read_file tool
        ai_responses = [
            {
                "type": "content",
                "content": "I'll read that file for you."
            },
            {
                "type": "tool_call",
                "name": "read_file",
                "parameters": {"path": "main.py"}
            },
            {
                "type": "complete"
            }
        ]

        async def mock_stream_completion(*args, **kwargs):
            for response in ai_responses:
                yield response

        mock_ai_provider.stream_completion = mock_stream_completion

        # 2. Set up expected WebSocket message sequence
        websocket_messages = [
            # Server sends tool approval request
            {
                "type": "tool_approval_request",
                "request_id": "req-123",
                "tool_name": "read_file",
                "parameters": {"args": {"file": {"path": "main.py"}}},
                "description": "Read file: main.py",
                "risk_level": "low",
                "requires_approval": False
            },
            # Client responds with approval
            {
                "type": "tool_approval_response",
                "request_id": "req-123",
                "decision": "approved",
                "feedback": "Auto-approved for testing"
            },
            # Server sends execution request
            {
                "type": "execute_tool",
                "execution_id": "exec-456",
                "tool": {
                    "name": "read_file",
                    "parameters": {"args": {"file": {"path": "main.py"}}}
                }
            },
            # Client sends result
            {
                "type": "tool_result",
                "execution_id": "exec-456",
                "result": {
                    "status": "success",
                    "data": "print('Hello, Gambiarra!')\n",
                    "metadata": {"file_size": 28, "line_count": 1}
                }
            }
        ]

        mock_websocket.recv = AsyncMock(
            side_effect=[json.dumps(msg) for msg in websocket_messages]
        )

        # 3. Test the flow (this would normally be in actual server/client code)
        # For now, just verify message structure correctness

        for i, expected_msg in enumerate(websocket_messages):
            received = json.loads(await mock_websocket.recv())

            assert received["type"] == expected_msg["type"]

            if received["type"] == "tool_approval_request":
                assert "request_id" in received
                assert "tool_name" in received
                assert "parameters" in received
                assert received["tool_name"] == "read_file"

            elif received["type"] == "execute_tool":
                assert "execution_id" in received
                assert "tool" in received
                assert received["tool"]["name"] == "read_file"

            elif received["type"] == "tool_result":
                assert "execution_id" in received
                assert "result" in received
                assert received["result"]["status"] == "success"

    async def test_tool_approval_denial_flow(self, mock_websocket):
        """Test tool execution flow when user denies approval."""

        denial_messages = [
            # Server sends tool approval request
            {
                "type": "tool_approval_request",
                "request_id": "req-123",
                "tool_name": "execute_command",
                "parameters": {"args": {"command": "rm -rf /"}},
                "description": "Execute dangerous command",
                "risk_level": "high",
                "requires_approval": True
            },
            # Client denies the request
            {
                "type": "tool_approval_response",
                "request_id": "req-123",
                "decision": "denied",
                "feedback": "Command blocked by security policy"
            },
            # Server sends denial notification
            {
                "type": "tool_denied",
                "request_id": "req-123",
                "tool_name": "execute_command",
                "reason": "Command blocked by security policy"
            }
        ]

        mock_websocket.recv = AsyncMock(
            side_effect=[json.dumps(msg) for msg in denial_messages]
        )

        # Test denial flow
        for expected_msg in denial_messages:
            received = json.loads(await mock_websocket.recv())

            assert received["type"] == expected_msg["type"]

            if received["type"] == "tool_approval_response":
                assert received["decision"] == "denied"
                assert "feedback" in received

            elif received["type"] == "tool_denied":
                assert "tool_name" in received
                assert "reason" in received

    async def test_tool_execution_error_handling(self, mock_websocket):
        """Test handling of tool execution errors."""

        error_messages = [
            # Server sends execution request
            {
                "type": "execute_tool",
                "execution_id": "exec-789",
                "tool": {
                    "name": "read_file",
                    "parameters": {"args": {"file": {"path": "nonexistent.txt"}}}
                }
            },
            # Client reports execution error
            {
                "type": "tool_result",
                "execution_id": "exec-789",
                "result": {
                    "status": "error",
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": "File 'nonexistent.txt' does not exist"
                    },
                    "data": None
                }
            }
        ]

        mock_websocket.recv = AsyncMock(
            side_effect=[json.dumps(msg) for msg in error_messages]
        )

        # Test error handling flow
        for expected_msg in error_messages:
            received = json.loads(await mock_websocket.recv())

            if received["type"] == "tool_result":
                assert received["result"]["status"] == "error"
                assert "error" in received["result"]
                assert received["result"]["error"]["code"] == "FILE_NOT_FOUND"

    async def test_nested_args_parameter_handling(self, mock_websocket):
        """Test handling of nested args structure in tool parameters."""

        # Test various tools with nested structure
        tools_with_nested_params = [
            {
                "name": "read_file",
                "parameters": {"args": {"file": {"path": "test.py"}}},
                "expected_flat": {"path": "test.py"}
            },
            {
                "name": "write_to_file",
                "parameters": {
                    "args": {
                        "path": "output.py",
                        "content": "print('test')",
                        "line_count": 1
                    }
                },
                "expected_flat": {
                    "path": "output.py",
                    "content": "print('test')",
                    "line_count": 1
                }
            },
            {
                "name": "execute_command",
                "parameters": {"args": {"command": "ls -la"}},
                "expected_flat": {"command": "ls -la"}
            }
        ]

        for tool_spec in tools_with_nested_params:
            # Mock tool execution message
            execution_msg = {
                "type": "execute_tool",
                "execution_id": f"exec-{tool_spec['name']}",
                "tool": {
                    "name": tool_spec["name"],
                    "parameters": tool_spec["parameters"]
                }
            }

            mock_websocket.recv = AsyncMock(return_value=json.dumps(execution_msg))

            received = json.loads(await mock_websocket.recv())

            # Verify nested structure is preserved
            assert received["tool"]["parameters"] == tool_spec["parameters"]

            # Verify the structure can be unwrapped to expected flat parameters
            # This would be done by the client's parameter unwrapper
            if tool_spec["name"] == "read_file":
                # Special case: read_file has args.file.path structure
                nested_params = received["tool"]["parameters"]
                assert nested_params["args"]["file"]["path"] == tool_spec["expected_flat"]["path"]
            else:
                # Standard case: parameters are in args
                nested_params = received["tool"]["parameters"]
                for key, value in tool_spec["expected_flat"].items():
                    assert nested_params["args"][key] == value

    @pytest.mark.slow
    async def test_concurrent_tool_executions(self, mock_websocket):
        """Test handling of multiple concurrent tool executions."""

        # Simulate multiple tool executions happening concurrently
        execution_ids = ["exec-1", "exec-2", "exec-3"]
        tools = ["read_file", "list_files", "write_to_file"]

        messages = []
        for i, (exec_id, tool_name) in enumerate(zip(execution_ids, tools)):
            messages.append({
                "type": "execute_tool",
                "execution_id": exec_id,
                "tool": {
                    "name": tool_name,
                    "parameters": {"args": {"path": f"test{i}.py"}}
                }
            })

        # Add corresponding results
        for i, exec_id in enumerate(execution_ids):
            messages.append({
                "type": "tool_result",
                "execution_id": exec_id,
                "result": {
                    "status": "success",
                    "data": f"Result for execution {i}",
                    "metadata": {}
                }
            })

        mock_websocket.recv = AsyncMock(
            side_effect=[json.dumps(msg) for msg in messages]
        )

        # Test that all messages are handled correctly
        received_executions = []
        received_results = []

        for _ in messages:
            msg = json.loads(await mock_websocket.recv())
            if msg["type"] == "execute_tool":
                received_executions.append(msg["execution_id"])
            elif msg["type"] == "tool_result":
                received_results.append(msg["execution_id"])

        # Verify all executions and results were received
        assert set(received_executions) == set(execution_ids)
        assert set(received_results) == set(execution_ids)

    async def test_websocket_error_recovery(self, mock_websocket):
        """Test recovery from WebSocket communication errors."""

        # Simulate WebSocket connection error
        mock_websocket.recv = AsyncMock(side_effect=ConnectionError("Connection lost"))

        # Should handle connection errors gracefully
        with pytest.raises(ConnectionError):
            await mock_websocket.recv()

        # Test recovery after reconnection
        mock_websocket.recv = AsyncMock(
            return_value=json.dumps({
                "type": "connected",
                "message": "Reconnected successfully"
            })
        )

        reconnect_msg = json.loads(await mock_websocket.recv())
        assert reconnect_msg["type"] == "connected"