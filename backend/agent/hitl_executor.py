"""
HITL Executor - Execute Approved Operations

Executes operations after user approval.
Part of the async HITL refactoring (Phase 4).

The executor:
1. Gets approved operations from HITLStore
2. Executes the tool logic directly
3. Updates operation status (completed/failed)
4. Notifies via WebSocket

Usage:
    executor = HITLExecutor(store, ws_manager)
    result = await executor.execute_operation(operation_id, project_path)
"""

import logging
from pathlib import Path
from typing import Optional

from agent.hitl_store import HITLStore, PendingOperation, OperationStatus, get_hitl_store
from agent.hitl_ws import HITLWebSocketManager, get_hitl_ws_manager
from agent.errors import ToolError, ErrorCode

logger = logging.getLogger(__name__)


class HITLExecutor:
    """
    Executes approved HITL operations.

    When a user approves an operation, the executor:
    1. Validates the operation is approved
    2. Executes the tool logic
    3. Updates status to completed/failed
    4. Notifies frontend via WebSocket

    This separates execution from the agent loop, allowing
    operations to be executed after the agent has moved on.
    """

    def __init__(
        self,
        store: Optional[HITLStore] = None,
        ws_manager: Optional[HITLWebSocketManager] = None,
    ):
        self.store = store or get_hitl_store()
        self.ws_manager = ws_manager or get_hitl_ws_manager()

    async def execute_operation(
        self,
        operation_id: str,
        project_path: str,
    ) -> str:
        """
        Execute an approved operation.

        Args:
            operation_id: ID of the operation to execute
            project_path: Path to the project

        Returns:
            Result message

        Raises:
            ValueError: If operation not found or not approved
        """
        # Get operation
        operation = await self.store.get_operation(operation_id)

        if not operation:
            raise ValueError(f"Operation not found: {operation_id}")

        if operation.status != OperationStatus.APPROVED:
            raise ValueError(f"Operation not approved: {operation.status.value}")

        # Mark as executing
        await self.store.update_execution_status(
            operation_id,
            OperationStatus.EXECUTING,
        )

        try:
            # Execute based on tool type
            if operation.tool_name == "edit_file":
                result = await self._execute_edit_file(operation, project_path)
            elif operation.tool_name == "write_file":
                result = await self._execute_write_file(operation, project_path)
            else:
                raise ValueError(f"Unknown tool: {operation.tool_name}")

            # Mark as completed
            await self.store.update_execution_status(
                operation_id,
                OperationStatus.COMPLETED,
                result=result,
            )

            # Notify via WebSocket
            await self.ws_manager.notify_execution_result(
                operation.session_id,
                operation_id,
                OperationStatus.COMPLETED,
                result=result,
            )

            logger.info(f"Executed operation {operation_id}: {result}")
            return result

        except Exception as e:
            error_msg = str(e)

            # Mark as failed
            await self.store.update_execution_status(
                operation_id,
                OperationStatus.FAILED,
                error=error_msg,
            )

            # Notify via WebSocket
            await self.ws_manager.notify_execution_result(
                operation.session_id,
                operation_id,
                OperationStatus.FAILED,
                error=error_msg,
            )

            logger.error(f"Failed to execute operation {operation_id}: {error_msg}")
            raise

    async def _execute_edit_file(
        self,
        operation: PendingOperation,
        project_path: str,
    ) -> str:
        """
        Execute edit_file operation.

        Logic extracted from pydantic_agent.py edit_file tool.
        """
        args = operation.tool_args
        filepath = args.get("filepath", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")

        if not filepath:
            raise ToolError(ErrorCode.INVALID_INPUT, "filepath is required")

        full_path = Path(project_path) / filepath

        # Security: ensure path is within project
        try:
            full_path.resolve().relative_to(Path(project_path).resolve())
        except ValueError:
            raise ToolError(ErrorCode.PATH_ESCAPE, f"Path escapes project directory: {filepath}")

        if not full_path.exists():
            raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")

        try:
            content = full_path.read_text()

            if old_string not in content:
                raise ToolError(ErrorCode.INVALID_INPUT, f"Could not find the specified text in {filepath}")

            count = content.count(old_string)
            if count > 1:
                raise ToolError(
                    ErrorCode.INVALID_INPUT,
                    f"Found {count} occurrences. Please provide more context for unique match.",
                    details={"count": count}
                )

            new_content = content.replace(old_string, new_string, 1)
            full_path.write_text(new_content)

            return f"Successfully edited {filepath}"

        except PermissionError:
            raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot write to file: {filepath}")

    async def _execute_write_file(
        self,
        operation: PendingOperation,
        project_path: str,
    ) -> str:
        """
        Execute write_file operation.

        Logic extracted from pydantic_agent.py write_file tool.
        """
        args = operation.tool_args
        filepath = args.get("filepath", "")
        content = args.get("content", "")

        if not filepath:
            raise ToolError(ErrorCode.INVALID_INPUT, "filepath is required")

        full_path = Path(project_path) / filepath

        # Security: ensure path is within project
        try:
            full_path.resolve().relative_to(Path(project_path).resolve())
        except ValueError:
            raise ToolError(ErrorCode.PATH_ESCAPE, f"Path escapes project directory: {filepath}")

        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            full_path.write_text(content)

            return f"Successfully wrote {filepath}"

        except PermissionError:
            raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot write to file: {filepath}")

    async def execute_batch(
        self,
        operation_ids: list[str],
        project_path: str,
    ) -> dict[str, dict]:
        """
        Execute multiple approved operations.

        Args:
            operation_ids: List of operation IDs to execute
            project_path: Path to the project

        Returns:
            Dict mapping operation_id to result dict with success/error
        """
        results = {}

        for op_id in operation_ids:
            try:
                result = await self.execute_operation(op_id, project_path)
                results[op_id] = {"success": True, "result": result}
            except Exception as e:
                results[op_id] = {"success": False, "error": str(e)}

        return results


# =============================================================================
# Singleton
# =============================================================================

_default_executor: Optional[HITLExecutor] = None


def get_hitl_executor() -> HITLExecutor:
    """Get or create the default HITL executor."""
    global _default_executor
    if _default_executor is None:
        _default_executor = HITLExecutor()
    return _default_executor


def reset_hitl_executor() -> None:
    """Reset the HITL executor (useful for testing)."""
    global _default_executor
    _default_executor = None
