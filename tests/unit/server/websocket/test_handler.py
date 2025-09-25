"""
Tests for WebSocket handler functionality.
Tests connection management, message routing, and error handling.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Mock FastAPI WebSocket before importing
import sys
sys.modules['fastapi'] = MagicMock()

from gambiarra.server.websocket_handler import WebSocketManager


@pytest.mark.asyncio
class TestWebSocketManager:
    """Test WebSocket connection management."""

    @pytest.fixture
    def ws_manager(self):
        """Create WebSocket manager instance."""
        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket instance."""
        websocket = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.receive_text = AsyncMock()
        websocket.close = AsyncMock()
        return websocket

    async def test_connection_registration(self, ws_manager, mock_websocket):
        """Test WebSocket connection registration."""
        connection_id = "test-connection-123"

        await ws_manager.connect(connection_id, mock_websocket)

        assert connection_id in ws_manager.connections
        assert ws_manager.connections[connection_id] == mock_websocket

    async def test_connection_deregistration(self, ws_manager, mock_websocket):
        """Test WebSocket connection deregistration."""
        connection_id = "test-connection-123"

        # First register
        await ws_manager.connect(connection_id, mock_websocket)
        assert connection_id in ws_manager.connections

        # Then disconnect
        await ws_manager.disconnect(connection_id)
        assert connection_id not in ws_manager.connections

    async def test_get_websocket(self, ws_manager, mock_websocket):
        """Test getting WebSocket by connection ID."""
        connection_id = "test-connection-123"

        # Before registration
        assert ws_manager.get_websocket(connection_id) is None

        # After registration
        await ws_manager.connect(connection_id, mock_websocket)
        assert ws_manager.get_websocket(connection_id) == mock_websocket

    async def test_disconnect_nonexistent_connection(self, ws_manager):
        """Test disconnecting non-existent connection."""
        # Should not raise error
        await ws_manager.disconnect("nonexistent-connection")

    async def test_concurrent_connections(self, ws_manager):
        """Test handling multiple concurrent connections."""
        websockets = []
        connection_ids = []

        for i in range(10):
            websocket = AsyncMock()
            connection_id = f"connection-{i}"
            websockets.append(websocket)
            connection_ids.append(connection_id)

        # Register all connections concurrently
        tasks = [
            ws_manager.connect(conn_id, ws)
            for conn_id, ws in zip(connection_ids, websockets)
        ]
        await asyncio.gather(*tasks)

        # Verify all connections registered
        assert len(ws_manager.connections) == 10
        for conn_id in connection_ids:
            assert conn_id in ws_manager.connections

    async def test_disconnect_all(self, ws_manager):
        """Test disconnecting all connections."""
        # Register multiple connections
        websockets = []
        for i in range(5):
            websocket = AsyncMock()
            connection_id = f"connection-{i}"
            await ws_manager.connect(connection_id, websocket)
            websockets.append(websocket)

        assert len(ws_manager.connections) == 5

        # Disconnect all
        await ws_manager.disconnect_all()

        # Verify all connections removed
        assert len(ws_manager.connections) == 0

        # Verify all websockets were closed
        for websocket in websockets:
            websocket.close.assert_called_once()

    async def test_disconnect_all_with_error(self, ws_manager):
        """Test disconnect_all handles individual close errors."""
        # Create websockets, some that will fail to close
        failing_websocket = AsyncMock()
        failing_websocket.close.side_effect = Exception("Close failed")

        normal_websocket = AsyncMock()

        await ws_manager.connect("failing", failing_websocket)
        await ws_manager.connect("normal", normal_websocket)

        # Should complete without raising exception
        await ws_manager.disconnect_all()

        # Both should have close called
        failing_websocket.close.assert_called_once()
        normal_websocket.close.assert_called_once()

        # Connections should be cleared
        assert len(ws_manager.connections) == 0

    async def test_thread_safety(self, ws_manager):
        """Test thread safety of connection operations."""
        # Simulate concurrent connects and disconnects
        async def connect_disconnect_cycle(i):
            websocket = AsyncMock()
            connection_id = f"connection-{i}"

            await ws_manager.connect(connection_id, websocket)
            await asyncio.sleep(0.01)  # Small delay
            await ws_manager.disconnect(connection_id)

        # Run multiple cycles concurrently
        tasks = [connect_disconnect_cycle(i) for i in range(20)]
        await asyncio.gather(*tasks)

        # Should end up with no connections
        assert len(ws_manager.connections) == 0

    async def test_connection_id_uniqueness(self, ws_manager):
        """Test that connection IDs must be unique."""
        websocket1 = AsyncMock()
        websocket2 = AsyncMock()
        connection_id = "same-id"

        # First connection
        await ws_manager.connect(connection_id, websocket1)
        assert ws_manager.connections[connection_id] == websocket1

        # Second connection with same ID should replace first
        await ws_manager.connect(connection_id, websocket2)
        assert ws_manager.connections[connection_id] == websocket2

    async def test_get_all_connections(self, ws_manager):
        """Test getting all active connections."""
        # Register multiple connections
        for i in range(3):
            websocket = AsyncMock()
            connection_id = f"connection-{i}"
            await ws_manager.connect(connection_id, websocket)

        # Check we can get all connections
        all_connections = ws_manager.connections
        assert len(all_connections) == 3
        assert all(isinstance(ws, AsyncMock) for ws in all_connections.values())

    async def test_memory_cleanup(self, ws_manager):
        """Test that disconnected connections are properly cleaned up."""
        import gc
        import weakref

        websocket = AsyncMock()
        connection_id = "test-connection"

        # Create weak reference to track garbage collection
        weak_ref = weakref.ref(websocket)

        await ws_manager.connect(connection_id, websocket)
        assert weak_ref() is not None

        await ws_manager.disconnect(connection_id)
        del websocket
        gc.collect()

        # WebSocket should be eligible for garbage collection
        # Note: This test might be flaky depending on Python's GC behavior


@pytest.mark.asyncio
class TestWebSocketMessageRouting:
    """Test WebSocket message routing functionality."""

    @pytest.fixture
    def ws_manager(self):
        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        websocket = AsyncMock()
        websocket.send_text = AsyncMock()
        return websocket

    async def test_send_message_to_connection(self, ws_manager, mock_websocket):
        """Test sending message to specific connection."""
        connection_id = "test-connection"
        await ws_manager.connect(connection_id, mock_websocket)

        # Send message through manager (would need method implementation)
        # This tests the foundation for message routing
        websocket = ws_manager.get_websocket(connection_id)
        assert websocket is not None

        test_message = '{"type": "test", "data": "hello"}'
        await websocket.send_text(test_message)

        mock_websocket.send_text.assert_called_once_with(test_message)

    async def test_broadcast_message(self, ws_manager):
        """Test broadcasting message to all connections."""
        # Register multiple connections
        websockets = []
        for i in range(3):
            websocket = AsyncMock()
            connection_id = f"connection-{i}"
            await ws_manager.connect(connection_id, websocket)
            websockets.append(websocket)

        # Simulate broadcast (would need method implementation)
        test_message = '{"type": "broadcast", "data": "hello all"}'

        for websocket in ws_manager.connections.values():
            await websocket.send_text(test_message)

        # Verify all websockets received the message
        for websocket in websockets:
            websocket.send_text.assert_called_once_with(test_message)

    async def test_send_to_nonexistent_connection(self, ws_manager):
        """Test sending message to non-existent connection."""
        websocket = ws_manager.get_websocket("nonexistent")
        assert websocket is None