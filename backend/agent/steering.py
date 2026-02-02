"""
Steering Messages for Agent Guidance

Allows users to send instructions while the agent is running.
Steering messages are queued and injected into the conversation
to redirect or guide the agent's behavior.

Architecture:
    1. User sends steering message via API
    2. Message is queued in SteeringManager with priority
    3. Streaming runner checks for pending steering
    4. Steering is injected as user interrupt message
    5. Agent processes the steering in its next turn

Usage:
    # Add steering message (from API)
    manager = get_steering_manager()
    await manager.add("Focus on fixing the bibliography first", priority=1)

    # In streaming runner
    steering = await manager.get_pending()
    if steering:
        # Inject steering into conversation
        ...

Priority Levels:
    0 - Normal (default) - processed in order
    1 - High - processed before normal messages
    2 - Urgent - interrupt current task
"""

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SteeringConfig:
    """Configuration for steering messages."""

    # Maximum messages in queue (oldest dropped if exceeded)
    max_queue_size: int = 20

    # Default priority for new messages
    default_priority: int = 0

    # Format for injected steering (can customize prefix/suffix)
    message_template: str = "[USER STEERING - Priority {priority}]: {content}"

    # Whether to combine multiple steering into single message
    combine_messages: bool = True


# =============================================================================
# Steering Types
# =============================================================================

@dataclass
class SteeringMessage:
    """A steering message from the user."""

    # Unique identifier
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Message content
    content: str = ""

    # Priority (higher = more urgent)
    priority: int = 0

    # Timestamp
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Session ID (for isolation)
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "session_id": self.session_id,
        }


# =============================================================================
# Steering Manager
# =============================================================================

class SteeringManager:
    """
    Manages steering message queue.

    Thread-safe manager that handles:
    - Queuing steering messages with priority
    - Retrieving and clearing pending messages
    - Session isolation
    - Event notification when steering arrives

    Usage:
        manager = SteeringManager()

        # Add steering message
        await manager.add("Focus on the abstract first", priority=1)

        # Check for pending steering
        if await manager.has_pending():
            messages = await manager.get_pending()
            steering_text = manager.format_steering(messages)
    """

    def __init__(self, config: SteeringConfig | None = None):
        self.config = config or SteeringConfig()

        # Queue of pending messages (deque for efficient operations)
        self._queue: deque[SteeringMessage] = deque()

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Event for notifying when steering arrives
        self._steering_event = asyncio.Event()

        # Callback for immediate notification
        self._on_steering_callback: Optional[Callable] = None

    def set_on_steering_callback(self, callback: Callable):
        """Set callback that fires when steering message is added."""
        self._on_steering_callback = callback

    async def add(
        self,
        content: str,
        priority: int | None = None,
        session_id: str | None = None,
    ) -> SteeringMessage:
        """
        Add a steering message to the queue.

        Args:
            content: The steering instruction
            priority: Message priority (default from config)
            session_id: Optional session ID for isolation

        Returns:
            The created SteeringMessage
        """
        if priority is None:
            priority = self.config.default_priority

        message = SteeringMessage(
            content=content,
            priority=priority,
            session_id=session_id,
        )

        async with self._lock:
            self._queue.append(message)

            # Sort by priority (higher first), then by time (older first)
            sorted_queue = sorted(
                self._queue,
                key=lambda m: (-m.priority, m.created_at),
            )
            self._queue = deque(sorted_queue)

            # Trim if over max size
            while len(self._queue) > self.config.max_queue_size:
                dropped = self._queue.pop()  # Remove lowest priority/oldest
                logger.warning(f"Steering queue full, dropped: {dropped.content[:50]}...")

            # Signal that steering is available
            self._steering_event.set()

        logger.info(f"Steering added: priority={priority}, content={content[:50]}...")

        # Fire callback if set
        if self._on_steering_callback:
            try:
                await self._on_steering_callback(message)
            except Exception as e:
                logger.error(f"Steering callback error: {e}")

        return message

    async def get_pending(
        self,
        session_id: str | None = None,
        clear: bool = True,
    ) -> list[SteeringMessage]:
        """
        Get all pending steering messages.

        Args:
            session_id: If provided, only return messages for this session
            clear: Whether to clear returned messages from queue (default: True)

        Returns:
            List of pending messages, sorted by priority then time
        """
        async with self._lock:
            if session_id:
                # Filter by session
                matching = [m for m in self._queue if m.session_id == session_id or m.session_id is None]
                if clear:
                    self._queue = deque(m for m in self._queue if m not in matching)
            else:
                matching = list(self._queue)
                if clear:
                    self._queue.clear()

            # Clear the event if queue is empty
            if not self._queue:
                self._steering_event.clear()

            return matching

    async def has_pending(self, session_id: str | None = None) -> bool:
        """
        Check if there are pending steering messages.

        Args:
            session_id: If provided, check only for this session

        Returns:
            True if pending messages exist
        """
        async with self._lock:
            if session_id:
                return any(
                    m.session_id == session_id or m.session_id is None
                    for m in self._queue
                )
            return len(self._queue) > 0

    async def peek(self, session_id: str | None = None) -> list[SteeringMessage]:
        """
        Peek at pending messages without removing them.

        Args:
            session_id: If provided, only return messages for this session

        Returns:
            List of pending messages
        """
        return await self.get_pending(session_id=session_id, clear=False)

    async def clear(self, session_id: str | None = None) -> int:
        """
        Clear pending steering messages.

        Args:
            session_id: If provided, only clear messages for this session

        Returns:
            Number of messages cleared
        """
        async with self._lock:
            if session_id:
                original_len = len(self._queue)
                self._queue = deque(
                    m for m in self._queue
                    if m.session_id is not None and m.session_id != session_id
                )
                cleared = original_len - len(self._queue)
            else:
                cleared = len(self._queue)
                self._queue.clear()

            if not self._queue:
                self._steering_event.clear()

            return cleared

    async def wait_for_steering(self, timeout: float | None = None) -> bool:
        """
        Wait for steering message to arrive.

        Args:
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            True if steering arrived, False if timeout
        """
        try:
            if timeout:
                await asyncio.wait_for(self._steering_event.wait(), timeout=timeout)
            else:
                await self._steering_event.wait()
            return True
        except asyncio.TimeoutError:
            return False

    def format_steering(
        self,
        messages: list[SteeringMessage],
        combine: bool | None = None,
    ) -> str:
        """
        Format steering messages for injection into conversation.

        Args:
            messages: List of steering messages
            combine: Whether to combine into single message (default from config)

        Returns:
            Formatted steering text ready for injection
        """
        if not messages:
            return ""

        if combine is None:
            combine = self.config.combine_messages

        formatted = []
        for msg in messages:
            text = self.config.message_template.format(
                priority=msg.priority,
                content=msg.content,
            )
            formatted.append(text)

        if combine:
            return "\n\n".join(formatted)
        else:
            return formatted[0] if formatted else ""

    def queue_size(self) -> int:
        """Get current queue size (without lock, for monitoring)."""
        return len(self._queue)


# =============================================================================
# Integration Functions
# =============================================================================

async def check_and_inject_steering(
    steering_manager: SteeringManager,
    message: str,
    session_id: str | None = None,
) -> tuple[str, list[SteeringMessage]]:
    """
    Check for steering and prepend to message if present.

    This is a convenience function for the streaming runner.

    Args:
        steering_manager: The steering manager to check
        message: Original user message
        session_id: Optional session ID for isolation

    Returns:
        Tuple of (modified_message, steering_messages_used)
    """
    if not await steering_manager.has_pending(session_id):
        return message, []

    steering_messages = await steering_manager.get_pending(session_id)
    if not steering_messages:
        return message, []

    steering_text = steering_manager.format_steering(steering_messages)

    # Prepend steering to original message
    combined = f"{steering_text}\n\n---\n\nUser's original request: {message}"

    logger.info(f"Injected {len(steering_messages)} steering messages")
    return combined, steering_messages


async def create_steering_from_context(
    content: str,
    priority: int = 1,
) -> str:
    """
    Create a formatted steering injection for immediate use.

    This bypasses the queue for cases where steering needs to be
    added directly to a message without going through the manager.

    Args:
        content: The steering instruction
        priority: Priority level for formatting

    Returns:
        Formatted steering text
    """
    config = SteeringConfig()
    return config.message_template.format(
        priority=priority,
        content=content,
    )


# =============================================================================
# Singleton Manager
# =============================================================================

_default_manager: SteeringManager | None = None


def get_steering_manager() -> SteeringManager:
    """Get or create the default steering manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = SteeringManager()
    return _default_manager


def reset_steering_manager():
    """Reset the steering manager (useful for testing)."""
    global _default_manager
    _default_manager = None
