"""
Connection pooling for efficient resource management.
Provides connection reuse and batching capabilities.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Generic, TypeVar
from dataclasses import dataclass
from abc import ABC, abstractmethod
import aiohttp
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class PoolConfig:
    """Configuration for connection pool."""
    min_size: int = 1
    max_size: int = 10
    max_idle_time: float = 300.0  # 5 minutes
    connection_timeout: float = 30.0
    max_retries: int = 3
    health_check_interval: float = 60.0


class Connection(ABC, Generic[T]):
    """Abstract base class for pooled connections."""

    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.created_at = time.time()
        self.last_used = time.time()
        self.use_count = 0
        self.is_healthy = True

    @abstractmethod
    async def connect(self) -> bool:
        """Establish the connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if connection is healthy."""
        pass

    @abstractmethod
    async def execute(self, operation: str, *args, **kwargs) -> Any:
        """Execute an operation using this connection."""
        pass

    def mark_used(self) -> None:
        """Mark connection as used."""
        self.last_used = time.time()
        self.use_count += 1

    def is_idle_expired(self, max_idle_time: float) -> bool:
        """Check if connection has been idle too long."""
        return (time.time() - self.last_used) > max_idle_time

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        age = time.time() - self.created_at
        idle_time = time.time() - self.last_used

        return {
            "connection_id": self.connection_id,
            "age_seconds": age,
            "idle_seconds": idle_time,
            "use_count": self.use_count,
            "is_healthy": self.is_healthy
        }


class HTTPConnection(Connection):
    """HTTP connection implementation."""

    def __init__(self, connection_id: str, base_url: str, headers: Dict[str, str] = None):
        super().__init__(connection_id)
        self.base_url = base_url
        self.headers = headers or {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> bool:
        """Establish HTTP connection."""
        try:
            connector = aiohttp.TCPConnector(
                limit=10,
                ttl_dns_cache=300,
                use_dns_cache=True
            )

            timeout = aiohttp.ClientTimeout(total=30)

            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.headers
            )

            # Test connection with a simple request
            async with self.session.get(f"{self.base_url}/health") as response:
                self.is_healthy = response.status < 500

            return self.is_healthy

        except Exception as e:
            logger.error(f"Failed to establish HTTP connection: {e}")
            self.is_healthy = False
            return False

    async def disconnect(self) -> None:
        """Close HTTP connection."""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    async def health_check(self) -> bool:
        """Check HTTP connection health."""
        if not self.session or self.session.closed:
            self.is_healthy = False
            return False

        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                self.is_healthy = response.status < 500
                return self.is_healthy
        except Exception:
            self.is_healthy = False
            return False

    async def execute(self, operation: str, *args, **kwargs) -> Any:
        """Execute HTTP operation."""
        if not self.session or self.session.closed:
            raise RuntimeError("Connection not established")

        self.mark_used()

        method = operation.upper()
        url = args[0] if args else kwargs.get('url')

        if not url.startswith('http'):
            url = f"{self.base_url}{url}"

        async with self.session.request(method, url, **kwargs) as response:
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "data": await response.text()
            }


class ConnectionPool(Generic[T]):
    """Generic connection pool implementation."""

    def __init__(self, name: str, config: PoolConfig, connection_factory: Callable):
        self.name = name
        self.config = config
        self.connection_factory = connection_factory

        self.available_connections: List[Connection] = []
        self.in_use_connections: Dict[str, Connection] = {}
        self.total_created = 0

        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the connection pool."""
        logger.info(f"Starting connection pool: {self.name}")

        # Create minimum connections
        async with self._lock:
            for i in range(self.config.min_size):
                connection = await self._create_connection()
                if connection:
                    self.available_connections.append(connection)

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info(f"Connection pool started: {self.name} ({len(self.available_connections)} connections)")

    async def stop(self) -> None:
        """Stop the connection pool."""
        logger.info(f"Stopping connection pool: {self.name}")

        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        async with self._lock:
            all_connections = self.available_connections + list(self.in_use_connections.values())

            for connection in all_connections:
                try:
                    await connection.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting connection {connection.connection_id}: {e}")

            self.available_connections.clear()
            self.in_use_connections.clear()

        logger.info(f"Connection pool stopped: {self.name}")

    @asynccontextmanager
    async def get_connection(self):
        """Get a connection from the pool."""
        connection = await self._acquire_connection()
        try:
            yield connection
        finally:
            await self._release_connection(connection)

    async def _acquire_connection(self) -> Connection:
        """Acquire a connection from the pool."""
        async with self._lock:
            # Try to get an available connection
            if self.available_connections:
                connection = self.available_connections.pop(0)
                self.in_use_connections[connection.connection_id] = connection
                return connection

            # Create new connection if under max size
            if len(self.in_use_connections) < self.config.max_size:
                connection = await self._create_connection()
                if connection:
                    self.in_use_connections[connection.connection_id] = connection
                    return connection

        # Wait for a connection to become available
        while True:
            await asyncio.sleep(0.1)
            async with self._lock:
                if self.available_connections:
                    connection = self.available_connections.pop(0)
                    self.in_use_connections[connection.connection_id] = connection
                    return connection

    async def _release_connection(self, connection: Connection) -> None:
        """Release a connection back to the pool."""
        async with self._lock:
            if connection.connection_id in self.in_use_connections:
                del self.in_use_connections[connection.connection_id]

                # Check if connection is still healthy
                if connection.is_healthy and not connection.is_idle_expired(self.config.max_idle_time):
                    self.available_connections.append(connection)
                else:
                    # Disconnect unhealthy or expired connection
                    try:
                        await connection.disconnect()
                    except Exception:
                        pass

    async def _create_connection(self) -> Optional[Connection]:
        """Create a new connection."""
        try:
            connection_id = f"{self.name}_{self.total_created}"
            connection = self.connection_factory(connection_id)

            if await connection.connect():
                self.total_created += 1
                logger.debug(f"Created connection: {connection_id}")
                return connection
            else:
                logger.error(f"Failed to connect: {connection_id}")
                return None

        except Exception as e:
            logger.error(f"Error creating connection: {e}")
            return None

    async def _health_check_loop(self) -> None:
        """Periodic health check for connections."""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_checks()
                await self._cleanup_expired_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def _perform_health_checks(self) -> None:
        """Perform health checks on available connections."""
        async with self._lock:
            unhealthy_connections = []

            for connection in self.available_connections:
                if not await connection.health_check():
                    unhealthy_connections.append(connection)

            # Remove unhealthy connections
            for connection in unhealthy_connections:
                self.available_connections.remove(connection)
                try:
                    await connection.disconnect()
                except Exception:
                    pass

            if unhealthy_connections:
                logger.info(f"Removed {len(unhealthy_connections)} unhealthy connections")

    async def _cleanup_expired_connections(self) -> None:
        """Clean up expired idle connections."""
        async with self._lock:
            expired_connections = []

            for connection in self.available_connections:
                if connection.is_idle_expired(self.config.max_idle_time):
                    expired_connections.append(connection)

            # Remove expired connections
            for connection in expired_connections:
                self.available_connections.remove(connection)
                try:
                    await connection.disconnect()
                except Exception:
                    pass

            if expired_connections:
                logger.debug(f"Cleaned up {len(expired_connections)} expired connections")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return {
            "name": self.name,
            "available_connections": len(self.available_connections),
            "in_use_connections": len(self.in_use_connections),
            "total_created": self.total_created,
            "config": {
                "min_size": self.config.min_size,
                "max_size": self.config.max_size,
                "max_idle_time": self.config.max_idle_time
            }
        }


class ConnectionPoolManager:
    """Manages multiple connection pools."""

    def __init__(self):
        self.pools: Dict[str, ConnectionPool] = {}
        self.logger = logging.getLogger(__name__)

    def create_http_pool(self, name: str, base_url: str, config: PoolConfig = None) -> ConnectionPool:
        """Create an HTTP connection pool."""
        config = config or PoolConfig()

        def connection_factory(connection_id: str) -> HTTPConnection:
            return HTTPConnection(connection_id, base_url)

        pool = ConnectionPool(name, config, connection_factory)
        self.pools[name] = pool

        self.logger.info(f"Created HTTP connection pool: {name}")
        return pool

    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """Get a connection pool by name."""
        return self.pools.get(name)

    async def start_all(self) -> None:
        """Start all connection pools."""
        for pool in self.pools.values():
            await pool.start()

    async def stop_all(self) -> None:
        """Stop all connection pools."""
        for pool in self.pools.values():
            await pool.stop()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all pools."""
        return {
            name: pool.get_stats()
            for name, pool in self.pools.items()
        }


# Global connection pool manager
_connection_pool_manager = ConnectionPoolManager()


def get_connection_pool_manager() -> ConnectionPoolManager:
    """Get the global connection pool manager."""
    return _connection_pool_manager