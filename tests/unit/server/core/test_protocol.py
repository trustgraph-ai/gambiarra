"""
Tests for server communication protocol functionality.
Tests message flow, protocol compliance, and bidirectional communication.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from gambiarra.server.core.protocol import (
    ProtocolHandler, MessageType, ProtocolMessage, ProtocolError,
    ConnectionState, MessageQueue
)


class TestProtocolMessage:
    """Test ProtocolMessage data structure."""

    def test_protocol_message_creation(self):
        """Test creating a protocol message."""
        message = ProtocolMessage(
            type=MessageType.USER_MESSAGE,
            content="Hello, assistant!",
            session_id="session-123"
        )

        assert message.type == MessageType.USER_MESSAGE
        assert message.content == "Hello, assistant!"
        assert message.session_id == "session-123"
        assert message.message_id is not None
        assert message.timestamp is not None

    def test_protocol_message_with_metadata(self):
        """Test protocol message with metadata."""
        metadata = {"client_version": "1.0.0", "platform": "web"}
        message = ProtocolMessage(
            type=MessageType.TOOL_APPROVAL_REQUEST,
            content={"tool": "read_file", "path": "test.py"},
            session_id="session-123",
            metadata=metadata
        )

        assert message.metadata == metadata
        assert message.metadata["client_version"] == "1.0.0"

    def test_protocol_message_serialization(self):
        """Test protocol message JSON serialization."""
        message = ProtocolMessage(
            type=MessageType.AI_RESPONSE,
            content="I'll help you with that",
            session_id="session-123"
        )

        json_str = message.to_json()
        parsed = json.loads(json_str)

        assert parsed["type"] == "AI_RESPONSE"
        assert parsed["content"] == "I'll help you with that"
        assert parsed["session_id"] == "session-123"
        assert "message_id" in parsed
        assert "timestamp" in parsed

    def test_protocol_message_deserialization(self):
        """Test protocol message JSON deserialization."""
        json_data = {
            "type": "USER_MESSAGE",
            "content": "Hello world",
            "session_id": "session-456",
            "message_id": "msg-789",
            "timestamp": 1638360000.0
        }

        message = ProtocolMessage.from_dict(json_data)

        assert message.type == MessageType.USER_MESSAGE
        assert message.content == "Hello world"
        assert message.session_id == "session-456"
        assert message.message_id == "msg-789"
        assert message.timestamp == 1638360000.0

    def test_invalid_message_type(self):
        """Test handling of invalid message type."""
        with pytest.raises(ValueError, match="Invalid message type"):
            ProtocolMessage(
                type="INVALID_TYPE",
                content="test",
                session_id="session-123"
            )

    def test_message_validation(self):
        """Test message validation."""
        # Valid message
        valid_message = ProtocolMessage(
            type=MessageType.USER_MESSAGE,
            content="Hello",
            session_id="session-123"
        )
        assert valid_message.is_valid()

        # Invalid - empty session ID
        invalid_message = ProtocolMessage(
            type=MessageType.USER_MESSAGE,
            content="Hello",
            session_id=""
        )
        assert not invalid_message.is_valid()


class TestConnectionState:
    """Test ConnectionState management."""

    def test_connection_state_creation(self):
        """Test creating connection state."""
        state = ConnectionState(
            connection_id="conn-123",
            session_id="session-456"
        )

        assert state.connection_id == "conn-123"
        assert state.session_id == "session-456"
        assert state.status == "connected"
        assert state.last_heartbeat is not None
        assert state.message_count == 0

    def test_connection_state_updates(self):
        """Test updating connection state."""
        state = ConnectionState(
            connection_id="conn-123",
            session_id="session-456"
        )

        # Update heartbeat
        old_heartbeat = state.last_heartbeat
        state.update_heartbeat()
        assert state.last_heartbeat > old_heartbeat

        # Update message count
        state.increment_message_count()
        assert state.message_count == 1

        # Update status
        state.set_status("disconnected")
        assert state.status == "disconnected"

    def test_connection_state_timeout_check(self):
        """Test connection timeout detection."""
        state = ConnectionState(
            connection_id="conn-123",
            session_id="session-456"
        )

        # Fresh connection should not be timed out
        assert not state.is_timed_out(timeout=30)

        # Simulate old heartbeat
        import time
        state.last_heartbeat = time.time() - 60  # 1 minute ago

        # Should be timed out with 30 second timeout
        assert state.is_timed_out(timeout=30)


class TestMessageQueue:
    """Test MessageQueue functionality."""

    def test_message_queue_creation(self):
        """Test creating message queue."""
        queue = MessageQueue(max_size=100)

        assert queue.max_size == 100
        assert queue.size() == 0
        assert queue.is_empty()

    def test_message_queue_operations(self):
        """Test basic queue operations."""
        queue = MessageQueue(max_size=10)

        message1 = ProtocolMessage(
            type=MessageType.USER_MESSAGE,
            content="First message",
            session_id="session-123"
        )
        message2 = ProtocolMessage(
            type=MessageType.AI_RESPONSE,
            content="Second message",
            session_id="session-123"
        )

        # Enqueue messages
        queue.enqueue(message1)
        queue.enqueue(message2)

        assert queue.size() == 2
        assert not queue.is_empty()

        # Dequeue messages
        dequeued1 = queue.dequeue()
        assert dequeued1.content == "First message"
        assert queue.size() == 1

        dequeued2 = queue.dequeue()
        assert dequeued2.content == "Second message"
        assert queue.size() == 0
        assert queue.is_empty()

    def test_message_queue_overflow(self):
        """Test message queue overflow handling."""
        queue = MessageQueue(max_size=2)

        # Fill queue to capacity
        for i in range(2):
            message = ProtocolMessage(
                type=MessageType.USER_MESSAGE,
                content=f"Message {i}",
                session_id="session-123"
            )
            queue.enqueue(message)

        # Queue should be full
        assert queue.is_full()

        # Adding another message should either drop oldest or raise error
        overflow_message = ProtocolMessage(
            type=MessageType.USER_MESSAGE,
            content="Overflow message",
            session_id="session-123"
        )

        try:
            queue.enqueue(overflow_message)
            # If it succeeds, oldest message should be dropped
            assert queue.size() == 2
        except Exception:
            # Or it should raise an exception
            assert queue.size() == 2

    def test_message_queue_priority(self):
        """Test message queue priority handling."""
        queue = MessageQueue(max_size=10, priority_enabled=True)

        # Add messages with different priorities
        low_priority = ProtocolMessage(
            type=MessageType.USER_MESSAGE,
            content="Low priority",
            session_id="session-123",
            priority=1
        )
        high_priority = ProtocolMessage(
            type=MessageType.TOOL_APPROVAL_REQUEST,
            content="High priority",
            session_id="session-123",
            priority=10
        )

        queue.enqueue(low_priority)
        queue.enqueue(high_priority)

        # High priority should come out first
        first = queue.dequeue()
        assert first.content == "High priority"

        second = queue.dequeue()
        assert second.content == "Low priority"


@pytest.mark.asyncio
class TestProtocolHandler:
    """Test ProtocolHandler functionality."""

    @pytest.fixture
    def protocol_handler(self):
        """Create ProtocolHandler instance."""
        return ProtocolHandler()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        websocket = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.receive_text = AsyncMock()
        websocket.close = AsyncMock()
        return websocket

    async def test_handle_connection(self, protocol_handler, mock_websocket):
        """Test handling new WebSocket connection."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        assert connection_id in protocol_handler.connections
        connection_state = protocol_handler.connections[connection_id]
        assert connection_state.session_id == session_id
        assert connection_state.status == "connected"

    async def test_handle_disconnection(self, protocol_handler, mock_websocket):
        """Test handling WebSocket disconnection."""
        connection_id = "conn-123"
        session_id = "session-456"

        # First connect
        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)
        assert connection_id in protocol_handler.connections

        # Then disconnect
        await protocol_handler.handle_disconnection(connection_id)
        assert connection_id not in protocol_handler.connections

    async def test_send_message(self, protocol_handler, mock_websocket):
        """Test sending message through protocol handler."""
        connection_id = "conn-123"
        session_id = "session-456"

        # Setup connection
        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Send message
        message = ProtocolMessage(
            type=MessageType.AI_RESPONSE,
            content="Hello from server",
            session_id=session_id
        )

        await protocol_handler.send_message(connection_id, message)

        mock_websocket.send_text.assert_called_once()
        sent_data = mock_websocket.send_text.call_args[0][0]
        parsed_data = json.loads(sent_data)
        assert parsed_data["content"] == "Hello from server"

    async def test_receive_message(self, protocol_handler, mock_websocket):
        """Test receiving message through protocol handler."""
        connection_id = "conn-123"
        session_id = "session-456"

        # Setup connection
        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Mock incoming message
        incoming_message = {
            "type": "USER_MESSAGE",
            "content": "Hello from client",
            "session_id": session_id
        }
        mock_websocket.receive_text.return_value = json.dumps(incoming_message)

        # Receive message
        received_message = await protocol_handler.receive_message(connection_id)

        assert received_message.type == MessageType.USER_MESSAGE
        assert received_message.content == "Hello from client"
        assert received_message.session_id == session_id

    async def test_receive_invalid_message(self, protocol_handler, mock_websocket):
        """Test handling of invalid incoming message."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Mock invalid JSON
        mock_websocket.receive_text.return_value = "invalid json"

        with pytest.raises(ProtocolError, match="Invalid message format"):
            await protocol_handler.receive_message(connection_id)

    async def test_broadcast_message(self, protocol_handler):
        """Test broadcasting message to multiple connections."""
        # Setup multiple connections
        websockets = []
        connection_ids = []

        for i in range(3):
            websocket = AsyncMock()
            websocket.send_text = AsyncMock()
            connection_id = f"conn-{i}"
            session_id = f"session-{i}"

            await protocol_handler.handle_connection(connection_id, session_id, websocket)
            websockets.append(websocket)
            connection_ids.append(connection_id)

        # Broadcast message
        message = ProtocolMessage(
            type=MessageType.SYSTEM_NOTIFICATION,
            content="Server maintenance in 5 minutes",
            session_id="system"
        )

        await protocol_handler.broadcast_message(message)

        # Verify all websockets received the message
        for websocket in websockets:
            websocket.send_text.assert_called_once()

    async def test_send_to_session(self, protocol_handler):
        """Test sending message to all connections in a session."""
        session_id = "session-123"

        # Setup multiple connections for same session
        websockets = []
        for i in range(2):
            websocket = AsyncMock()
            websocket.send_text = AsyncMock()
            connection_id = f"conn-{i}"

            await protocol_handler.handle_connection(connection_id, session_id, websocket)
            websockets.append(websocket)

        # Send message to session
        message = ProtocolMessage(
            type=MessageType.AI_RESPONSE,
            content="Response for session",
            session_id=session_id
        )

        await protocol_handler.send_to_session(session_id, message)

        # All connections in session should receive message
        for websocket in websockets:
            websocket.send_text.assert_called_once()

    async def test_heartbeat_mechanism(self, protocol_handler, mock_websocket):
        """Test heartbeat mechanism for connection monitoring."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Send heartbeat
        await protocol_handler.send_heartbeat(connection_id)

        # Verify heartbeat message was sent
        mock_websocket.send_text.assert_called_once()
        sent_data = mock_websocket.send_text.call_args[0][0]
        parsed_data = json.loads(sent_data)
        assert parsed_data["type"] == "HEARTBEAT"

    async def test_connection_timeout_cleanup(self, protocol_handler, mock_websocket):
        """Test cleanup of timed out connections."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Simulate old connection by modifying heartbeat
        connection_state = protocol_handler.connections[connection_id]
        import time
        connection_state.last_heartbeat = time.time() - 120  # 2 minutes ago

        # Run timeout cleanup
        timed_out = await protocol_handler.cleanup_timed_out_connections(timeout=60)

        assert connection_id in timed_out
        assert connection_id not in protocol_handler.connections

    async def test_message_ordering(self, protocol_handler, mock_websocket):
        """Test that messages maintain proper ordering."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Send multiple messages quickly
        messages = []
        for i in range(5):
            message = ProtocolMessage(
                type=MessageType.AI_RESPONSE,
                content=f"Message {i}",
                session_id=session_id
            )
            messages.append(message)
            await protocol_handler.send_message(connection_id, message)

        # Verify all messages were sent in order
        assert mock_websocket.send_text.call_count == 5

        sent_messages = []
        for call in mock_websocket.send_text.call_args_list:
            sent_data = call[0][0]
            parsed_data = json.loads(sent_data)
            sent_messages.append(parsed_data["content"])

        expected_order = [f"Message {i}" for i in range(5)]
        assert sent_messages == expected_order

    async def test_concurrent_message_handling(self, protocol_handler):
        """Test handling of concurrent messages."""
        # Setup multiple connections
        websockets = []
        connection_ids = []

        for i in range(10):
            websocket = AsyncMock()
            websocket.send_text = AsyncMock()
            connection_id = f"conn-{i}"
            session_id = f"session-{i}"

            await protocol_handler.handle_connection(connection_id, session_id, websocket)
            websockets.append(websocket)
            connection_ids.append(connection_id)

        # Send messages concurrently to all connections
        async def send_message_to_connection(conn_id):
            message = ProtocolMessage(
                type=MessageType.AI_RESPONSE,
                content=f"Message to {conn_id}",
                session_id=f"session-{conn_id.split('-')[1]}"
            )
            await protocol_handler.send_message(conn_id, message)

        tasks = [send_message_to_connection(conn_id) for conn_id in connection_ids]
        await asyncio.gather(*tasks)

        # Verify all websockets received their messages
        for websocket in websockets:
            websocket.send_text.assert_called_once()

    async def test_protocol_error_handling(self, protocol_handler, mock_websocket):
        """Test protocol error handling and recovery."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Simulate websocket send error
        mock_websocket.send_text.side_effect = Exception("Connection broken")

        message = ProtocolMessage(
            type=MessageType.AI_RESPONSE,
            content="Test message",
            session_id=session_id
        )

        # Should handle error gracefully
        with pytest.raises(ProtocolError):
            await protocol_handler.send_message(connection_id, message)

    async def test_message_validation_and_sanitization(self, protocol_handler, mock_websocket):
        """Test message validation and sanitization."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Test various potentially problematic messages
        test_cases = [
            # XSS attempt
            {"type": "USER_MESSAGE", "content": "<script>alert('xss')</script>", "session_id": session_id},
            # SQL injection attempt
            {"type": "USER_MESSAGE", "content": "'; DROP TABLE users; --", "session_id": session_id},
            # Very long content
            {"type": "USER_MESSAGE", "content": "x" * 100000, "session_id": session_id},
        ]

        for test_case in test_cases:
            mock_websocket.receive_text.return_value = json.dumps(test_case)

            try:
                received_message = await protocol_handler.receive_message(connection_id)
                # Message should be sanitized or validated
                assert received_message is not None
            except ProtocolError:
                # Or rejected as invalid
                pass

    async def test_session_isolation(self, protocol_handler):
        """Test that sessions are properly isolated."""
        # Setup connections for different sessions
        session_1_websockets = []
        session_2_websockets = []

        for i in range(2):
            # Session 1 connections
            ws1 = AsyncMock()
            ws1.send_text = AsyncMock()
            conn_id_1 = f"session1-conn-{i}"
            await protocol_handler.handle_connection(conn_id_1, "session-1", ws1)
            session_1_websockets.append(ws1)

            # Session 2 connections
            ws2 = AsyncMock()
            ws2.send_text = AsyncMock()
            conn_id_2 = f"session2-conn-{i}"
            await protocol_handler.handle_connection(conn_id_2, "session-2", ws2)
            session_2_websockets.append(ws2)

        # Send message to session 1 only
        message = ProtocolMessage(
            type=MessageType.AI_RESPONSE,
            content="Message for session 1",
            session_id="session-1"
        )

        await protocol_handler.send_to_session("session-1", message)

        # Only session 1 websockets should receive message
        for ws in session_1_websockets:
            ws.send_text.assert_called_once()

        for ws in session_2_websockets:
            ws.send_text.assert_not_called()

    async def test_protocol_statistics(self, protocol_handler, mock_websocket):
        """Test protocol statistics collection."""
        connection_id = "conn-123"
        session_id = "session-456"

        await protocol_handler.handle_connection(connection_id, session_id, mock_websocket)

        # Send some messages
        for i in range(5):
            message = ProtocolMessage(
                type=MessageType.AI_RESPONSE,
                content=f"Message {i}",
                session_id=session_id
            )
            await protocol_handler.send_message(connection_id, message)

        # Get statistics
        stats = protocol_handler.get_statistics()

        assert stats["total_connections"] >= 1
        assert stats["active_sessions"] >= 1
        assert stats["messages_sent"] >= 5
        assert "uptime" in stats

    def test_message_type_enum(self):
        """Test MessageType enum values."""
        expected_types = [
            "USER_MESSAGE",
            "AI_RESPONSE",
            "TOOL_APPROVAL_REQUEST",
            "TOOL_APPROVAL_RESPONSE",
            "TOOL_EXECUTION_RESULT",
            "SYSTEM_NOTIFICATION",
            "HEARTBEAT",
            "ERROR"
        ]

        for expected_type in expected_types:
            assert hasattr(MessageType, expected_type)
            assert getattr(MessageType, expected_type) == expected_type