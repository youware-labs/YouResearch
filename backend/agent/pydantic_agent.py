"""
PydanticAI-based Aura Agent

Main agent implementation using PydanticAI framework.
Tools are loaded from modular tool packages in agent/tools/.
"""

from typing import Any, Optional, TYPE_CHECKING

from pydantic_ai import Agent, RunContext

from agent.deps import AuraDeps
from agent.providers import get_default_model
from agent.prompts import get_system_prompt
from agent.processors import default_history_processor
from agent.logging import get_logger

logger = get_logger("agent")

if TYPE_CHECKING:
    from agent.hitl import ApprovalStatus


async def _check_hitl(
    ctx: RunContext[AuraDeps],
    tool_name: str,
    tool_args: dict[str, Any],
    file_path: Optional[str] = None,
    old_content: Optional[str] = None,
    new_content: Optional[str] = None,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """
    Check HITL approval for a tool call.

    Supports two modes:
    - blocking: Legacy mode, waits for approval (up to 5 minutes)
    - async: New mode, queues operation and returns immediately

    Args:
        ctx: Run context with dependencies
        tool_name: Name of the tool
        tool_args: Arguments for the tool
        file_path: File being modified (for diff preview, async mode)
        old_content: Content before operation (for diff preview, async mode)
        new_content: Content after operation (for diff preview, async mode)

    Returns:
        (should_proceed, message, modified_args)
        - blocking mode: should_proceed=True means approved, False means rejected/timeout
        - async mode: should_proceed=False, message contains "[PENDING:op_id]" status
    """
    hitl_mode = ctx.deps.hitl_mode

    # Async mode (new non-blocking)
    if hitl_mode == "async" and ctx.deps.hitl_store:
        hitl_store = ctx.deps.hitl_store
        hitl_ws = ctx.deps.hitl_ws

        if not hitl_store.needs_approval(tool_name):
            return True, None, None

        logger.info(f"HITL async: Queueing {tool_name} for approval")

        # Queue operation in store
        operation = await hitl_store.add_operation(
            session_id=ctx.deps.session_id,
            tool_name=tool_name,
            tool_args=tool_args,
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
        )

        # Notify via WebSocket
        if hitl_ws:
            await hitl_ws.notify_pending(operation)

        # Return immediately with pending status
        # Agent receives this as "operation queued" - not executed yet
        return False, f"[PENDING:{operation.operation_id}] {tool_name} queued for approval. File: {file_path or 'N/A'}", None

    # Blocking mode (legacy)
    hitl_manager = ctx.deps.hitl_manager

    # Debug logging
    logger.info(f"HITL check for {tool_name}: manager={hitl_manager}, needs_approval={hitl_manager.needs_approval(tool_name) if hitl_manager else 'N/A'}")

    if not hitl_manager or not hitl_manager.needs_approval(tool_name):
        return True, None, None

    from agent.hitl import ApprovalStatus
    import uuid

    logger.info(f"Requesting approval for {tool_name}")

    # Request approval
    approval = await hitl_manager.request_approval(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_call_id=str(uuid.uuid4()),
    )

    logger.info(f"Approval result: {approval.status}")

    if approval.status == ApprovalStatus.REJECTED:
        return False, f"Operation cancelled: {approval.rejection_reason}", None

    if approval.status == ApprovalStatus.TIMEOUT:
        return False, "Operation cancelled: Approval timeout", None

    # Return modified args if user edited them
    modified = approval.modified_args if approval.status == ApprovalStatus.MODIFIED else None
    return True, None, modified


# =============================================================================
# Agent Creation
# =============================================================================

# Create the main Aura agent
aura_agent = Agent(
    model=get_default_model(),
    deps_type=AuraDeps,
    retries=3,
    instructions=get_system_prompt,  # Dynamic instructions based on RunContext
    history_processors=[default_history_processor],  # Clean up message history
)


# =============================================================================
# Register All Tools
# =============================================================================

from agent.tools import register_all_tools

# Register all modular tools with the agent
# Tools are organized in agent/tools/:
#   - file_tools.py: read_file, edit_file, write_file, list_files, find_files, search_in_file, read_file_lines
#   - latex_tools.py: compile_latex, check_latex_syntax, create_table, create_figure, create_algorithm
#   - research_tools.py: read_pdf, delegate_to_subagent
#   - planning_tools.py: plan_task, get_current_plan, start_plan_execution, complete_plan_step, fail_plan_step, skip_plan_step, abandon_plan
#   - writing_tools.py: analyze_structure, add_citation
#   - utility_tools.py: think
register_all_tools(aura_agent, check_hitl_func=_check_hitl)
