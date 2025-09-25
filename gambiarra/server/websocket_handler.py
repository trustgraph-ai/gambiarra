"""
WebSocket connection management for Gambiarra server.
"""

import asyncio
import json
import logging
from typing import Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and message routing."""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, connection_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection."""
        async with self._lock:
            self.connections[connection_id] = websocket
            logger.info(f"📡 Registered WebSocket connection: {connection_id}")

    async def disconnect(self, connection_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if connection_id in self.connections:
                del self.connections[connection_id]
                logger.info(f"📡 Removed WebSocket connection: {connection_id}")

    async def disconnect_all(self) -> None:
        """Disconnect all WebSocket connections."""
        async with self._lock:
            connections_to_close = list(self.connections.values())
            self.connections.clear()

        # Close all connections
        for websocket in connections_to_close:
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"❌ Error closing WebSocket: {e}")

        logger.info(f"📡 Closed {len(connections_to_close)} WebSocket connections")

    def get_websocket(self, connection_id: str) -> Optional[WebSocket]:
        """Get WebSocket by connection ID."""
        return self.connections.get(connection_id)

    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.connections)

    async def send_to_connection(self, connection_id: str, message: dict) -> bool:
        """Send message to specific connection."""
        websocket = self.get_websocket(connection_id)
        if not websocket:
            logger.warning(f"📡 Connection {connection_id} not found")
            return False

        try:
            await websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"❌ Error sending to {connection_id}: {e}")
            # Remove the failed connection
            await self.disconnect(connection_id)
            return False

    async def broadcast(self, message: dict, exclude: Optional[str] = None) -> int:
        """Broadcast message to all connections."""
        sent_count = 0
        failed_connections = []

        for connection_id, websocket in self.connections.items():
            if exclude and connection_id == exclude:
                continue

            try:
                await websocket.send_text(json.dumps(message))
                sent_count += 1
            except Exception as e:
                logger.error(f"❌ Broadcast error to {connection_id}: {e}")
                failed_connections.append(connection_id)

        # Clean up failed connections
        for connection_id in failed_connections:
            await self.disconnect(connection_id)

        logger.info(f"📡 Broadcast to {sent_count} connections, {len(failed_connections)} failed")
        return sent_count

    def list_connections(self) -> list:
        """List all connection IDs."""
        return list(self.connections.keys())