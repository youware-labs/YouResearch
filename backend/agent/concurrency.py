"""
Concurrency Control - Resource Management

Provides asyncio-based concurrency controls for resource-intensive operations.
Prevents system overload by limiting concurrent operations.

Usage:
    from agent.concurrency import get_compilation_semaphore, get_api_semaphore

    async def compile_latex(...):
        async with get_compilation_semaphore():
            # Only N compilations can run concurrently
            ...

    async def call_api(...):
        async with get_api_semaphore():
            # Rate-limited API calls
            ...
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from contextlib import asynccontextmanager
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyConfig:
    """Configuration for concurrency limits."""

    # Maximum concurrent LaTeX compilations (Docker containers)
    max_compilations: int = 3

    # Maximum concurrent LLM API calls
    max_api_calls: int = 10

    # Maximum concurrent file operations
    max_file_ops: int = 20

    # Maximum concurrent subagent runs
    max_subagents: int = 5

    # Timeout for acquiring semaphore (seconds)
    acquire_timeout: float = 60.0


class ConcurrencyManager:
    """
    Manages concurrency limits for various operations.

    Features:
    - Semaphore-based limiting
    - Per-operation statistics
    - Timeout handling
    - Queue monitoring
    """

    def __init__(self, config: Optional[ConcurrencyConfig] = None):
        self.config = config or ConcurrencyConfig()
        self._compilation_sem = asyncio.Semaphore(self.config.max_compilations)
        self._api_sem = asyncio.Semaphore(self.config.max_api_calls)
        self._file_sem = asyncio.Semaphore(self.config.max_file_ops)
        self._subagent_sem = asyncio.Semaphore(self.config.max_subagents)

        # Statistics
        self._stats = {
            "compilation": {"current": 0, "total": 0, "peak": 0, "timeouts": 0},
            "api": {"current": 0, "total": 0, "peak": 0, "timeouts": 0},
            "file": {"current": 0, "total": 0, "peak": 0, "timeouts": 0},
            "subagent": {"current": 0, "total": 0, "peak": 0, "timeouts": 0},
        }

        # Wait time tracking
        self._wait_times: dict[str, deque] = {
            "compilation": deque(maxlen=100),
            "api": deque(maxlen=100),
            "file": deque(maxlen=100),
            "subagent": deque(maxlen=100),
        }

    @asynccontextmanager
    async def compilation_limit(self):
        """Context manager for LaTeX compilation limiting."""
        async with self._acquire_with_stats("compilation", self._compilation_sem):
            yield

    @asynccontextmanager
    async def api_limit(self):
        """Context manager for API call limiting."""
        async with self._acquire_with_stats("api", self._api_sem):
            yield

    @asynccontextmanager
    async def file_limit(self):
        """Context manager for file operation limiting."""
        async with self._acquire_with_stats("file", self._file_sem):
            yield

    @asynccontextmanager
    async def subagent_limit(self):
        """Context manager for subagent limiting."""
        async with self._acquire_with_stats("subagent", self._subagent_sem):
            yield

    @asynccontextmanager
    async def _acquire_with_stats(self, name: str, semaphore: asyncio.Semaphore):
        """
        Acquire semaphore with statistics tracking.

        Args:
            name: Name of the operation type
            semaphore: The semaphore to acquire
        """
        start_time = datetime.now()

        try:
            # Try to acquire with timeout
            acquired = await asyncio.wait_for(
                semaphore.acquire(),
                timeout=self.config.acquire_timeout
            )

            wait_time = (datetime.now() - start_time).total_seconds()
            self._wait_times[name].append(wait_time)

            # Update statistics
            self._stats[name]["current"] += 1
            self._stats[name]["total"] += 1
            self._stats[name]["peak"] = max(
                self._stats[name]["peak"],
                self._stats[name]["current"]
            )

            if wait_time > 1.0:
                logger.warning(f"{name} waited {wait_time:.2f}s for semaphore")

            try:
                yield
            finally:
                self._stats[name]["current"] -= 1
                semaphore.release()

        except asyncio.TimeoutError:
            self._stats[name]["timeouts"] += 1
            logger.error(f"{name} timed out waiting for semaphore")
            raise ConcurrencyTimeoutError(
                f"Timed out waiting for {name} slot after {self.config.acquire_timeout}s"
            )

    def get_stats(self) -> dict:
        """Get concurrency statistics."""
        result = {}
        for name, stats in self._stats.items():
            wait_times = list(self._wait_times[name])
            avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0

            result[name] = {
                **stats,
                "avg_wait_time": round(avg_wait, 3),
                "recent_wait_times": wait_times[-5:],  # Last 5
            }
        return result

    def get_availability(self) -> dict:
        """Get current availability for each operation type."""
        return {
            "compilation": {
                "available": self.config.max_compilations - self._stats["compilation"]["current"],
                "max": self.config.max_compilations,
            },
            "api": {
                "available": self.config.max_api_calls - self._stats["api"]["current"],
                "max": self.config.max_api_calls,
            },
            "file": {
                "available": self.config.max_file_ops - self._stats["file"]["current"],
                "max": self.config.max_file_ops,
            },
            "subagent": {
                "available": self.config.max_subagents - self._stats["subagent"]["current"],
                "max": self.config.max_subagents,
            },
        }


class ConcurrencyTimeoutError(Exception):
    """Raised when acquiring a semaphore times out."""
    pass


# Singleton instance
_concurrency_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """Get or create the singleton ConcurrencyManager instance."""
    global _concurrency_manager
    if _concurrency_manager is None:
        _concurrency_manager = ConcurrencyManager()
    return _concurrency_manager


# Convenience functions for direct semaphore access
def get_compilation_semaphore():
    """Get compilation limiter context manager."""
    return get_concurrency_manager().compilation_limit()


def get_api_semaphore():
    """Get API call limiter context manager."""
    return get_concurrency_manager().api_limit()


def get_file_semaphore():
    """Get file operation limiter context manager."""
    return get_concurrency_manager().file_limit()


def get_subagent_semaphore():
    """Get subagent limiter context manager."""
    return get_concurrency_manager().subagent_limit()
