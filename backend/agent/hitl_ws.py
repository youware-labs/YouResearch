"""
HITL WebSocket Handler

Provides real-time notifications for pending operations.
Part of the async HITL refactoring (Phase 4).

WebSocket messages:
- pending: New operation waiting for approval
- status: Operation status changed
- result: Execution result available

Usage:
    # In FastAPI
    @app.websocket("/ws/hitl/{session_id}")
    async def hitl_websocket(websocket: WebSocket, session_id: str):
        manager = get_hitl_ws_manager()
        await manager.connect(websocket, session_id)
        try:
            while True:
                await websocket.receive_text()  # Keep connection alive
        except WebSocketDisconnect:
            manager.disconnect(websocket, session_id)
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional
from weakref import WeakSet

from fastapi import WebSocket

from agent.hitl_store import PendingOperation, OperationStatus

logger = logging.getLogger(__name__)


@dataclass
class WSMessage:
    """WebSocket message format."""
    type: str  # "pending", "status", "result"
    data: dict[str, Any]

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "type": self.type,
            "data": self.data,
        })


class HITLWebSocketManager:
    """
    Manages WebSocket connections for HITL notifications.

    Each chat session can have multiple WebSocket connections
    (e.g., multiple browser tabs). Messages are broadcast to all
    connections for a given session.

    Thread-safe with asyncio.Lock.
    """

    def __init__(self):
        # Connections by session_id
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Accept a WebSocket connection and register it for a session.

        Args:
            websocket: The WebSocket connection
            session_id: Chat session to subscribe to
        """
        await websocket.accept()

        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(websocket)

        logger.info(f"HITL WebSocket connected for session {session_id}")

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            websocket: The WebSocket connection
            session_id: Chat session it was subscribed to
        """
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]

        logger.info(f"HITL WebSocket disconnected for session {session_id}")

    async def _send_to_session(self, session_id: str, message: WSMessage) -> int:
        """
        Send a message to all connections for a session.

        Args:
            session_id: Target session
            message: Message to send

        Returns:
            Number of connections that received the message
        """
        sent = 0
        dead_connections = []

        async with self._lock:
            connections = self._connections.get(session_id, set()).copy()

        for ws in connections:
            try:
                await ws.send_text(message.to_json())
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(ws)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                if session_id in self._connections:
                    for ws in dead_connections:
                        self._connections[session_id].discard(ws)

        return sent

    async def notify_pending(self, operation: PendingOperation) -> int:
        """
        Notify frontend of a new pending operation.

        Args:
            operation: The pending operation

        Returns:
            Number of connections notified
        """
        diff_preview = operation.get_diff_preview()

        message = WSMessage(
            type="pending",
            data={
                "operation_id": operation.operation_id,
                "session_id": operation.session_id,
                "tool_name": operation.tool_name,
                "tool_args": operation.tool_args,
                "file_path": operation.file_path,
                "diff_preview": diff_preview,
                "created_at": operation.created_at.isoformat(),
                "expires_at": operation.expires_at.isoformat(),
            },
        )

        sent = await self._send_to_session(operation.session_id, message)
        logger.info(f"Notified {sent} connections of pending operation {operation.operation_id}")
        return sent

    async def notify_status_change(self, operation: PendingOperation) -> int:
        """
        Notify frontend of a status change.

        Args:
            operation: The operation with updated status

        Returns:
            Number of connections notified
        """
        data = {
            "operation_id": operation.operation_id,
            "status": operation.status.value,
        }

        # Include additional info based on status
        if operation.status == OperationStatus.REJECTED:
            data["rejection_reason"] = operation.rejection_reason
        elif operation.status == OperationStatus.COMPLETED:
            data["result"] = operation.result
        elif operation.status == OperationStatus.FAILED:
            data["error"] = operation.error

        message = WSMessage(type="status", data=data)

        sent = await self._send_to_session(operation.session_id, message)
        logger.info(f"Notified {sent} connections of status change: {operation.operation_id} -> {operation.status.value}")
        return sent

    async def notify_execution_result(
        self,
        session_id: str,
        operation_id: str,
        status: OperationStatus,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> int:
        """
        Notify frontend of execution result.

        Args:
            session_id: Target session
            operation_id: The operation that was executed
            status: Final status (COMPLETED or FAILED)
            result: Result on success
            error: Error message on failure

        Returns:
            Number of connections notified
        """
        message = WSMessage(
            type="result",
            data={
                "operation_id": operation_id,
                "status": status.value,
                "result": result,
                "error": error,
            },
        )

        sent = await self._send_to_session(session_id, message)
        logger.info(f"Notified {sent} connections of execution result: {operation_id}")
        return sent

    async def get_connection_count(self, session_id: str) -> int:
        """Get number of active connections for a session."""
        async with self._lock:
            return len(self._connections.get(session_id, set()))

    async def get_all_session_ids(self) -> list[str]:
        """Get all session IDs with active connections."""
        async with self._lock:
            return list(self._connections.keys())


# =============================================================================
# Singleton
# =============================================================================

_default_manager: Optional[HITLWebSocketManager] = None


def get_hitl_ws_manager() -> HITLWebSocketManager:
    """Get or create the default WebSocket manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = HITLWebSocketManager()
    return _default_manager


def reset_hitl_ws_manager() -> None:
    """Reset the WebSocket manager (useful for testing)."""
    global _default_manager
    _default_manager = None
