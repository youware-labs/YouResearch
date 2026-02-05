"""
Connection Manager - HTTP Client Pooling

Manages HTTP client connections with proper pooling, cleanup, and lifecycle management.
Prevents connection leaks and optimizes HTTP performance.

Usage:
    manager = get_connection_manager()
    client = await manager.get_client("https://api.example.com")
    response = await client.get("/endpoint")
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    """Configuration for HTTP client."""
    timeout: float = 30.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 300.0  # 5 minutes
    retries: int = 3


@dataclass
class ManagedClient:
    """Wrapper for httpx client with metadata."""
    client: httpx.AsyncClient
    base_url: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    request_count: int = 0


class ConnectionManager:
    """
    Manages HTTP client connections with pooling and lifecycle management.

    Features:
    - Connection pooling per base URL
    - Automatic cleanup of idle connections
    - Configurable timeouts and limits
    - Thread-safe operations
    """

    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig()
        self._clients: dict[str, ManagedClient] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._closed = False

    async def get_client(self, base_url: str) -> httpx.AsyncClient:
        """
        Get or create an HTTP client for the given base URL.

        Args:
            base_url: The base URL for the client

        Returns:
            An httpx.AsyncClient configured for the base URL
        """
        if self._closed:
            raise RuntimeError("ConnectionManager is closed")

        async with self._lock:
            if base_url in self._clients:
                managed = self._clients[base_url]
                managed.last_used = datetime.now()
                managed.request_count += 1
                return managed.client

            # Create new client
            limits = httpx.Limits(
                max_connections=self.config.max_connections,
                max_keepalive_connections=self.config.max_keepalive_connections,
                keepalive_expiry=self.config.keepalive_expiry,
            )

            timeout = httpx.Timeout(self.config.timeout)

            client = httpx.AsyncClient(
                base_url=base_url,
                timeout=timeout,
                limits=limits,
                follow_redirects=True,
            )

            self._clients[base_url] = ManagedClient(
                client=client,
                base_url=base_url,
            )

            logger.debug(f"Created new HTTP client for {base_url}")
            return client

    async def remove_client(self, base_url: str) -> None:
        """
        Close and remove a specific client.

        Args:
            base_url: The base URL of the client to remove
        """
        async with self._lock:
            if base_url in self._clients:
                managed = self._clients.pop(base_url)
                await managed.client.aclose()
                logger.debug(f"Closed HTTP client for {base_url}")

    async def cleanup_idle(self, max_idle_seconds: int = 300) -> int:
        """
        Close clients that have been idle for too long.

        Args:
            max_idle_seconds: Maximum idle time before closing

        Returns:
            Number of clients cleaned up
        """
        now = datetime.now()
        max_idle = timedelta(seconds=max_idle_seconds)
        cleaned = 0

        async with self._lock:
            idle_urls = [
                url for url, managed in self._clients.items()
                if now - managed.last_used > max_idle
            ]

            for url in idle_urls:
                managed = self._clients.pop(url)
                await managed.client.aclose()
                cleaned += 1
                logger.debug(f"Cleaned up idle client for {url}")

        return cleaned

    async def close_all(self) -> None:
        """Close all managed clients."""
        self._closed = True

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for url, managed in self._clients.items():
                try:
                    await managed.client.aclose()
                    logger.debug(f"Closed HTTP client for {url}")
                except Exception as e:
                    logger.warning(f"Error closing client for {url}: {e}")

            self._clients.clear()

    def start_cleanup_task(self, interval_seconds: int = 60) -> None:
        """
        Start background task to periodically clean up idle connections.

        Args:
            interval_seconds: How often to run cleanup
        """
        if self._cleanup_task is not None:
            return

        async def cleanup_loop():
            while not self._closed:
                try:
                    await asyncio.sleep(interval_seconds)
                    cleaned = await self.cleanup_idle()
                    if cleaned > 0:
                        logger.info(f"Cleaned up {cleaned} idle connections")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    def get_stats(self) -> dict:
        """Get statistics about managed connections."""
        return {
            "total_clients": len(self._clients),
            "clients": {
                url: {
                    "created_at": managed.created_at.isoformat(),
                    "last_used": managed.last_used.isoformat(),
                    "request_count": managed.request_count,
                }
                for url, managed in self._clients.items()
            }
        }


# Singleton instance
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the singleton ConnectionManager instance."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
        _connection_manager.start_cleanup_task()
    return _connection_manager


async def close_connection_manager() -> None:
    """Close the singleton ConnectionManager."""
    global _connection_manager
    if _connection_manager is not None:
        await _connection_manager.close_all()
        _connection_manager = None
