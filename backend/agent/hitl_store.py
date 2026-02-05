"""
HITL Store - Pending Operation Storage

Stores operations that require user approval before execution.
Part of the async HITL refactoring (Phase 4).

Architecture:
- Operations enter store when tool requires approval
- User approves/rejects via REST or batch API
- Approved operations are executed by HITLExecutor
- WebSocket notifies frontend of changes
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional, Callable
from pathlib import Path


class OperationStatus(Enum):
    """Status of a pending operation."""
    PENDING = "pending"       # Waiting for user approval
    APPROVED = "approved"     # User approved, ready to execute
    REJECTED = "rejected"     # User rejected
    EXECUTING = "executing"   # Currently being executed
    COMPLETED = "completed"   # Successfully executed
    FAILED = "failed"         # Execution failed
    EXPIRED = "expired"       # Timed out waiting for approval


@dataclass
class PendingOperation:
    """
    An operation waiting for user approval.

    Contains all information needed to execute the operation after approval,
    plus diff preview data for the frontend.
    """
    # Identity
    operation_id: str
    session_id: str

    # Tool information
    tool_name: str
    tool_args: dict[str, Any]

    # Status tracking
    status: OperationStatus = OperationStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=30))
    resolved_at: Optional[datetime] = None

    # Execution result
    result: Optional[str] = None
    error: Optional[str] = None

    # Diff preview (for edit_file/write_file)
    file_path: Optional[str] = None
    old_content: Optional[str] = None  # Content before operation
    new_content: Optional[str] = None  # Content after operation

    # Rejection reason (if rejected)
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "operation_id": self.operation_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "result": self.result,
            "error": self.error,
            "file_path": self.file_path,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "rejection_reason": self.rejection_reason,
        }

    def get_diff_preview(self) -> dict | None:
        """
        Get diff preview for frontend display.

        Returns dict with old_content, new_content for diff highlighting,
        or None if not a file operation or no content available.
        """
        if not self.file_path:
            return None

        if self.tool_name in ("edit_file", "write_file") and (self.old_content is not None or self.new_content is not None):
            return {
                "file_path": self.file_path,
                "old_content": self.old_content or "",
                "new_content": self.new_content or "",
            }

        return None

    @property
    def is_expired(self) -> bool:
        """Check if this operation has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_pending(self) -> bool:
        """Check if this operation is still pending."""
        return self.status == OperationStatus.PENDING and not self.is_expired


@dataclass
class HITLStoreConfig:
    """Configuration for HITL store."""

    # Tools that require approval
    approval_required: set[str] = field(default_factory=lambda: {
        "write_file",
        "edit_file",
    })

    # Default timeout for approval (seconds)
    default_timeout: float = 1800.0  # 30 minutes

    # Cleanup expired operations after this many seconds
    cleanup_after: float = 3600.0  # 1 hour


class HITLStore:
    """
    Thread-safe store for pending operations.

    Manages the lifecycle of operations waiting for user approval:
    1. Tool adds operation via add_operation()
    2. Frontend receives notification via WebSocket
    3. User approves/rejects via REST API
    4. HITLExecutor executes approved operations
    5. Results are sent back via WebSocket

    Usage:
        store = HITLStore()

        # In tool
        op_id = await store.add_operation(
            session_id="abc123",
            tool_name="edit_file",
            tool_args={"filepath": "main.tex", ...},
            file_path="main.tex",
            old_content="...",
            new_content="...",
        )

        # In REST endpoint
        await store.approve(op_id)
        # or
        await store.reject(op_id, "User declined")
    """

    def __init__(self, config: HITLStoreConfig | None = None):
        self.config = config or HITLStoreConfig()

        # Operations by operation_id
        self._operations: dict[str, PendingOperation] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Callbacks for notifications
        self._on_operation_added: Optional[Callable] = None
        self._on_status_changed: Optional[Callable] = None

    def needs_approval(self, tool_name: str) -> bool:
        """Check if a tool requires approval."""
        return tool_name in self.config.approval_required

    def set_callbacks(
        self,
        on_operation_added: Optional[Callable] = None,
        on_status_changed: Optional[Callable] = None,
    ) -> None:
        """Set callbacks for operation events."""
        self._on_operation_added = on_operation_added
        self._on_status_changed = on_status_changed

    async def add_operation(
        self,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        file_path: Optional[str] = None,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> PendingOperation:
        """
        Add a new operation waiting for approval.

        Args:
            session_id: Chat session this belongs to
            tool_name: Name of the tool
            tool_args: Arguments for the tool
            file_path: File being modified (for diff preview)
            old_content: Content before operation
            new_content: Content after operation
            timeout: Custom timeout in seconds

        Returns:
            The created PendingOperation
        """
        operation_id = str(uuid.uuid4())
        timeout = timeout or self.config.default_timeout

        operation = PendingOperation(
            operation_id=operation_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=tool_args,
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=timeout),
        )

        async with self._lock:
            self._operations[operation_id] = operation

        # Notify callback
        if self._on_operation_added:
            await self._on_operation_added(operation)

        return operation

    async def get_operation(self, operation_id: str) -> Optional[PendingOperation]:
        """Get an operation by ID."""
        async with self._lock:
            op = self._operations.get(operation_id)
            if op and op.is_expired and op.status == OperationStatus.PENDING:
                # Mark as expired
                op.status = OperationStatus.EXPIRED
                op.resolved_at = datetime.now(timezone.utc)
            return op

    async def get_pending_by_session(self, session_id: str) -> list[PendingOperation]:
        """Get all pending operations for a session."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            result = []

            for op in self._operations.values():
                if op.session_id != session_id:
                    continue

                # Auto-expire if needed
                if op.status == OperationStatus.PENDING and now > op.expires_at:
                    op.status = OperationStatus.EXPIRED
                    op.resolved_at = now

                if op.status == OperationStatus.PENDING:
                    result.append(op)

            return sorted(result, key=lambda x: x.created_at)

    async def get_all_by_session(self, session_id: str) -> list[PendingOperation]:
        """Get all operations for a session (including resolved)."""
        async with self._lock:
            result = [
                op for op in self._operations.values()
                if op.session_id == session_id
            ]
            return sorted(result, key=lambda x: x.created_at, reverse=True)

    async def approve(
        self,
        operation_id: str,
        modified_args: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Approve a pending operation.

        Args:
            operation_id: The operation to approve
            modified_args: Optional modified arguments

        Returns:
            True if approved, False if not found or not pending
        """
        async with self._lock:
            op = self._operations.get(operation_id)

            if not op or op.status != OperationStatus.PENDING:
                return False

            if op.is_expired:
                op.status = OperationStatus.EXPIRED
                op.resolved_at = datetime.now(timezone.utc)
                return False

            op.status = OperationStatus.APPROVED
            op.resolved_at = datetime.now(timezone.utc)

            if modified_args:
                op.tool_args.update(modified_args)

        # Notify callback
        if self._on_status_changed:
            await self._on_status_changed(op)

        return True

    async def reject(
        self,
        operation_id: str,
        reason: str = "User rejected",
    ) -> bool:
        """
        Reject a pending operation.

        Args:
            operation_id: The operation to reject
            reason: Rejection reason

        Returns:
            True if rejected, False if not found or not pending
        """
        async with self._lock:
            op = self._operations.get(operation_id)

            if not op or op.status != OperationStatus.PENDING:
                return False

            op.status = OperationStatus.REJECTED
            op.rejection_reason = reason
            op.resolved_at = datetime.now(timezone.utc)

        # Notify callback
        if self._on_status_changed:
            await self._on_status_changed(op)

        return True

    async def batch_approve(
        self,
        operation_ids: list[str],
    ) -> dict[str, bool]:
        """
        Approve multiple operations at once.

        Args:
            operation_ids: List of operation IDs to approve

        Returns:
            Dict mapping operation_id to success status
        """
        results = {}
        for op_id in operation_ids:
            results[op_id] = await self.approve(op_id)
        return results

    async def batch_reject(
        self,
        operation_ids: list[str],
        reason: str = "User rejected",
    ) -> dict[str, bool]:
        """
        Reject multiple operations at once.

        Args:
            operation_ids: List of operation IDs to reject
            reason: Rejection reason

        Returns:
            Dict mapping operation_id to success status
        """
        results = {}
        for op_id in operation_ids:
            results[op_id] = await self.reject(op_id, reason)
        return results

    async def update_execution_status(
        self,
        operation_id: str,
        status: OperationStatus,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update operation status after execution.

        Args:
            operation_id: The operation to update
            status: New status (EXECUTING, COMPLETED, FAILED)
            result: Execution result on success
            error: Error message on failure

        Returns:
            True if updated, False if not found
        """
        async with self._lock:
            op = self._operations.get(operation_id)

            if not op:
                return False

            op.status = status
            if result:
                op.result = result
            if error:
                op.error = error

        # Notify callback
        if self._on_status_changed:
            await self._on_status_changed(op)

        return True

    async def cleanup_expired(self, max_age_seconds: Optional[float] = None) -> int:
        """
        Clean up old operations.

        Args:
            max_age_seconds: Remove operations older than this (default: config.cleanup_after)

        Returns:
            Number of operations removed
        """
        max_age = max_age_seconds or self.config.cleanup_after
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age)
        removed = 0

        async with self._lock:
            to_remove = []

            for op_id, op in self._operations.items():
                # Only remove non-pending operations that are old
                if op.status != OperationStatus.PENDING and op.created_at < cutoff:
                    to_remove.append(op_id)
                # Also remove expired pending operations
                elif op.status == OperationStatus.PENDING and op.is_expired:
                    op.status = OperationStatus.EXPIRED
                    op.resolved_at = datetime.now(timezone.utc)
                    if op.created_at < cutoff:
                        to_remove.append(op_id)

            for op_id in to_remove:
                del self._operations[op_id]
                removed += 1

        return removed


# =============================================================================
# Singleton
# =============================================================================

_default_store: Optional[HITLStore] = None


def get_hitl_store() -> HITLStore:
    """Get or create the default HITL store."""
    global _default_store
    if _default_store is None:
        _default_store = HITLStore()
    return _default_store


def reset_hitl_store() -> None:
    """Reset the HITL store (useful for testing)."""
    global _default_store
    _default_store = None
