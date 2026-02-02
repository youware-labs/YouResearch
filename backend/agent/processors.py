"""
History Processors for PydanticAI

These processors clean up and optimize message history before sending to LLM.
PydanticAI calls these functions to transform message history.

Usage:
    agent = Agent(
        ...,
        history_processors=[truncate_tool_results, remove_thinking_tools],
    )
"""

from copy import deepcopy
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ModelMessage,
    ToolReturnPart,
)

if TYPE_CHECKING:
    pass


# Type alias for message list
Messages = list[ModelRequest | ModelResponse]


# =============================================================================
# Truncation Processor
# =============================================================================

def truncate_tool_results(
    messages: Messages,
    max_chars: int = 4000,
) -> Messages:
    """
    Truncate long tool results to prevent context overflow.

    PydanticAI history processor that truncates ToolReturnPart content.

    Args:
        messages: List of ModelRequest/ModelResponse messages
        max_chars: Maximum characters for tool result content

    Returns:
        Messages with truncated tool results
    """
    result = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            # Check if any parts need truncation
            needs_truncation = False
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    content = _get_content_str(part.content)
                    if len(content) > max_chars:
                        needs_truncation = True
                        break

            if needs_truncation:
                # Create new message with truncated parts
                new_parts = []
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        content = _get_content_str(part.content)
                        if len(content) > max_chars:
                            truncated = content[:max_chars]
                            truncated += f"\n... [truncated {len(content) - max_chars} chars]"
                            new_part = ToolReturnPart(
                                tool_name=part.tool_name,
                                content=truncated,
                                tool_call_id=part.tool_call_id,
                                metadata=part.metadata,
                                timestamp=part.timestamp,
                            )
                            new_parts.append(new_part)
                        else:
                            new_parts.append(part)
                    else:
                        new_parts.append(part)

                # ModelRequest doesn't have timestamp in newer PydanticAI versions
                msg = ModelRequest(
                    parts=new_parts,
                    instructions=msg.instructions,
                    run_id=msg.run_id,
                    metadata=msg.metadata,
                )

            result.append(msg)
        else:
            result.append(msg)

    return result


def _get_content_str(content) -> str:
    """Convert content to string for length checking."""
    if isinstance(content, str):
        return content
    return str(content)


# =============================================================================
# Thinking Tool Processor
# =============================================================================

def remove_thinking_tools(messages: Messages) -> Messages:
    """
    Remove thinking tool calls and results from history.

    The think tool is for internal reasoning and doesn't need to persist
    in history, saving context tokens.

    IMPORTANT: This processor preserves message structure by keeping placeholder
    parts when removing think tools would leave a message empty. This ensures
    the alternating ModelRequest/ModelResponse pattern is maintained.

    Args:
        messages: List of ModelRequest/ModelResponse messages

    Returns:
        Messages with thinking tool calls removed (or replaced with placeholders)
    """
    from pydantic_ai.messages import ToolCallPart, TextPart, UserPromptPart

    result = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            # Filter out think tool return parts
            new_parts = [
                part for part in msg.parts
                if not (isinstance(part, ToolReturnPart) and part.tool_name == "think")
            ]

            # If filtering removed all parts, keep the message with original parts
            # to preserve message structure (alternating Request/Response pattern)
            if not new_parts:
                # Keep the original message to preserve structure
                result.append(msg)
            else:
                # ModelRequest doesn't have timestamp in newer PydanticAI versions
                msg = ModelRequest(
                    parts=new_parts,
                    instructions=msg.instructions,
                    run_id=msg.run_id,
                    metadata=msg.metadata,
                )
                result.append(msg)

        elif isinstance(msg, ModelResponse):
            # Filter out think tool call parts from response
            new_parts = [
                part for part in msg.parts
                if not (isinstance(part, ToolCallPart) and part.tool_name == "think")
            ]

            # If filtering removed all parts, keep the original message
            # to preserve message structure
            if not new_parts:
                # Keep the original message to preserve structure
                result.append(msg)
            else:
                msg = ModelResponse(
                    parts=new_parts,
                    usage=msg.usage,
                    model_name=msg.model_name,
                    timestamp=msg.timestamp,
                    provider_name=msg.provider_name,
                    finish_reason=msg.finish_reason,
                    run_id=msg.run_id,
                    metadata=msg.metadata,
                )
                result.append(msg)
        else:
            result.append(msg)

    return result


# =============================================================================
# Empty Message Removal
# =============================================================================

def remove_empty_messages(messages: Messages) -> Messages:
    """
    Remove messages with no meaningful content.

    NOTE: This is now a no-op to preserve message structure. Removing messages
    can break the alternating ModelRequest/ModelResponse pattern that PydanticAI
    requires. Empty messages are harmless and will be handled by the LLM.

    Args:
        messages: List of messages

    Returns:
        Same messages (no filtering applied)
    """
    # Don't remove messages - it can break the alternating pattern
    # that PydanticAI requires for proper operation
    return messages


# =============================================================================
# Combined Pipeline
# =============================================================================

def create_history_processor(
    max_tool_result_chars: int = 4000,
    remove_thinking: bool = False,  # Disabled by default - breaks tool_use/tool_result pairing
) -> callable:
    """
    Create a combined history processor with configurable options.

    Args:
        max_tool_result_chars: Maximum chars for tool results
        remove_thinking: Whether to remove think tool calls (disabled by default)

    Returns:
        History processor function
    """
    def process(messages: Messages) -> Messages:
        # Apply processors in sequence
        messages = truncate_tool_results(messages, max_chars=max_tool_result_chars)
        # NOTE: remove_thinking is disabled by default because it can break
        # the tool_use/tool_result pairing that Claude API requires
        if remove_thinking:
            messages = remove_thinking_tools(messages)
        # NOTE: remove_empty_messages is disabled - it breaks message alternation
        # messages = remove_empty_messages(messages)
        return messages

    return process


# Default processor - only truncates long tool results
default_history_processor = create_history_processor()
