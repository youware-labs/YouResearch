"""
Human-in-the-Loop (HITL) Support

Provides approval workflow for dangerous tool operations.
Users can approve, reject, or modify tool calls before execution.

Architecture:
    1. HITLConfig defines which tools require approval
    2. Tools check HITL before executing via requires_approval decorator
    3. If approval needed, ApprovalRequest is created and stream emits event
    4. Tool waits on asyncio.Event for approval/rejection
    5. HTTP endpoint receives approval and sets the event
    6. Tool continues with approval result

Usage:
    # In streaming runner
    hitl_manager = HITLManager()
    deps = AuraDeps(project_path=path, hitl_manager=hitl_manager)

    # In tool
    @requires_approval
    async def write_file(ctx: RunContext[AuraDeps], filepath: str, content: str) -> str:
        ...
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class HITLConfig:
    """Configuration for Human-in-the-Loop approval."""

    # Tools that require approval before execution
    approval_required: set[str] = field(default_factory=lambda: {
        "write_file",
        "edit_file",
    })

    # Tools that should show preview but not block
    preview_only: set[str] = field(default_factory=lambda: {
        "compile_latex",
    })

    # Timeout for waiting for approval (seconds)
    approval_timeout: float = 300.0  # 5 minutes

    # Auto-approve after timeout instead of rejecting
    auto_approve_on_timeout: bool = False


# =============================================================================
# Approval Types
# =============================================================================

class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMEOUT = "timeout"


@dataclass
class ApprovalRequest:
    """A pending approval request."""

    # Unique identifier for this request
    request_id: str

    # Tool information
    tool_name: str
    tool_args: dict[str, Any]
    tool_call_id: str

    # Status
    status: ApprovalStatus = ApprovalStatus.PENDING

    # Modified args (if user edited before approving)
    modified_args: Optional[dict[str, Any]] = None

    # Rejection reason
    rejection_reason: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_call_id": self.tool_call_id,
            "status": self.status.value,
            "modified_args": self.modified_args,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


# =============================================================================
# HITL Manager
# =============================================================================

class HITLManager:
    """
    Manages Human-in-the-Loop approval workflow.

    Thread-safe manager that handles:
    - Creating approval requests
    - Waiting for user response (with timeout)
    - Processing approvals/rejections
    - Cleanup of expired requests

    Usage:
        manager = HITLManager()

        # In tool (waits for approval)
        approval = await manager.request_approval(
            tool_name="write_file",
            tool_args={"filepath": "main.tex", "content": "..."},
            tool_call_id="call_123",
        )
        if approval.status == ApprovalStatus.APPROVED:
            # Execute tool
        else:
            return f"Rejected: {approval.rejection_reason}"

        # In HTTP handler (resolves approval)
        manager.approve("request_id_here")
        # or
        manager.reject("request_id_here", "User declined")
    """

    def __init__(self, config: HITLConfig | None = None):
        self.config = config or HITLConfig()

        # Pending requests by request_id
        self._pending: dict[str, ApprovalRequest] = {}

        # Events for async waiting
        self._events: dict[str, asyncio.Event] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Callback for emitting events (set by streaming runner)
        self._event_callback: Optional[Callable] = None

    def needs_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval."""
        return tool_name in self.config.approval_required

    def needs_preview(self, tool_name: str) -> bool:
        """Check if a tool should show preview (but not block)."""
        return tool_name in self.config.preview_only

    def set_event_callback(self, callback: Callable):
        """Set callback for emitting approval events to stream."""
        self._event_callback = callback

    async def request_approval(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str,
        timeout: float | None = None,
    ) -> ApprovalRequest:
        """
        Request approval for a tool call and wait for user response.

        This method:
        1. Creates an ApprovalRequest
        2. Emits an event to notify the frontend
        3. Waits for user to approve/reject (or timeout)
        4. Returns the resolved request

        Args:
            tool_name: Name of the tool requiring approval
            tool_args: Arguments being passed to the tool
            tool_call_id: PydanticAI's tool call ID
            timeout: Override default timeout (seconds)

        Returns:
            ApprovalRequest with final status (approved/rejected/timeout)
        """
        request_id = str(uuid.uuid4())
        timeout = timeout or self.config.approval_timeout

        request = ApprovalRequest(
            request_id=request_id,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call_id,
        )

        async with self._lock:
            self._pending[request_id] = request
            self._events[request_id] = asyncio.Event()

        logger.info(f"HITL: Requesting approval for {tool_name} (request_id={request_id})")

        # Emit event to notify frontend
        if self._event_callback:
            await self._event_callback(request)

        # Wait for approval or timeout
        try:
            await asyncio.wait_for(
                self._events[request_id].wait(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"HITL: Approval timeout for {request_id}")
            async with self._lock:
                if request_id in self._pending:
                    request = self._pending[request_id]
                    if self.config.auto_approve_on_timeout:
                        request.status = ApprovalStatus.APPROVED
                    else:
                        request.status = ApprovalStatus.TIMEOUT
                        request.rejection_reason = "Approval timeout"
                    request.resolved_at = datetime.now(timezone.utc)

        # Cleanup and return
        async with self._lock:
            self._events.pop(request_id, None)
            result = self._pending.pop(request_id, request)

        logger.info(f"HITL: Request {request_id} resolved with status {result.status.value}")
        return result

    async def approve(
        self,
        request_id: str,
        modified_args: dict[str, Any] | None = None,
    ) -> bool:
        """
        Approve a pending request.

        Args:
            request_id: The request to approve
            modified_args: Optional modified arguments (user edited before approving)

        Returns:
            True if request was found and approved, False otherwise
        """
        async with self._lock:
            if request_id not in self._pending:
                logger.warning(f"HITL: Cannot approve unknown request {request_id}")
                return False

            request = self._pending[request_id]

            if modified_args:
                request.status = ApprovalStatus.MODIFIED
                request.modified_args = modified_args
            else:
                request.status = ApprovalStatus.APPROVED

            request.resolved_at = datetime.now(timezone.utc)

            # Signal the waiting coroutine
            if request_id in self._events:
                self._events[request_id].set()

            logger.info(f"HITL: Approved request {request_id}")
            return True

    async def reject(
        self,
        request_id: str,
        reason: str = "User rejected",
    ) -> bool:
        """
        Reject a pending request.

        Args:
            request_id: The request to reject
            reason: Reason for rejection

        Returns:
            True if request was found and rejected, False otherwise
        """
        async with self._lock:
            if request_id not in self._pending:
                logger.warning(f"HITL: Cannot reject unknown request {request_id}")
                return False

            request = self._pending[request_id]
            request.status = ApprovalStatus.REJECTED
            request.rejection_reason = reason
            request.resolved_at = datetime.now(timezone.utc)

            # Signal the waiting coroutine
            if request_id in self._events:
                self._events[request_id].set()

            logger.info(f"HITL: Rejected request {request_id}: {reason}")
            return True

    async def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        async with self._lock:
            return [
                req for req in self._pending.values()
                if req.status == ApprovalStatus.PENDING
            ]

    async def get_request(self, request_id: str) -> ApprovalRequest | None:
        """Get a specific approval request."""
        async with self._lock:
            return self._pending.get(request_id)

    async def cleanup_expired(self, max_age_seconds: float = 600) -> int:
        """
        Clean up old resolved requests.

        Args:
            max_age_seconds: Remove requests older than this

        Returns:
            Number of requests removed
        """
        now = datetime.now(timezone.utc)
        removed = 0

        async with self._lock:
            to_remove = []
            for request_id, request in self._pending.items():
                if request.status != ApprovalStatus.PENDING:
                    age = (now - request.created_at).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(request_id)

            for request_id in to_remove:
                self._pending.pop(request_id, None)
                self._events.pop(request_id, None)
                removed += 1

        return removed


# =============================================================================
# Tool Decorator
# =============================================================================

def requires_approval(tool_func: Callable) -> Callable:
    """
    Decorator that adds HITL approval check to a tool.

    The decorated tool will:
    1. Check if HITL manager exists in deps
    2. If approval needed, wait for user approval
    3. Return rejection message if rejected
    4. Execute original tool if approved

    Usage:
        @aura_agent.tool
        @requires_approval
        async def write_file(ctx: RunContext[AuraDeps], filepath: str, content: str) -> str:
            # This code only runs if user approves
            ...

    Note: This decorator must be applied BEFORE @aura_agent.tool
    """
    import functools

    @functools.wraps(tool_func)
    async def wrapper(ctx, *args, **kwargs):
        # Check if HITL is enabled
        hitl_manager = getattr(ctx.deps, 'hitl_manager', None)

        if hitl_manager and hitl_manager.needs_approval(tool_func.__name__):
            # Get tool call ID from context if available
            tool_call_id = getattr(ctx, 'tool_call_id', str(uuid.uuid4()))

            # Request approval
            approval = await hitl_manager.request_approval(
                tool_name=tool_func.__name__,
                tool_args=kwargs,
                tool_call_id=tool_call_id,
            )

            if approval.status == ApprovalStatus.REJECTED:
                return f"Operation cancelled: {approval.rejection_reason}"

            if approval.status == ApprovalStatus.TIMEOUT:
                return "Operation cancelled: Approval timeout"

            # Use modified args if provided
            if approval.status == ApprovalStatus.MODIFIED and approval.modified_args:
                kwargs.update(approval.modified_args)

        # Execute the original tool
        return await tool_func(ctx, *args, **kwargs)

    return wrapper


# =============================================================================
# Singleton Manager
# =============================================================================

_default_manager: HITLManager | None = None


def get_hitl_manager() -> HITLManager:
    """Get or create the default HITL manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = HITLManager()
    return _default_manager


def reset_hitl_manager():
    """Reset the HITL manager (useful for testing)."""
    global _default_manager
    _default_manager = None
