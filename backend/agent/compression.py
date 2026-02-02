"""
Message Compression for Long Conversations

Automatically compresses old messages when approaching context limit.
Uses a smaller model (Haiku) to summarize conversation history.

Architecture:
    1. TokenCounter estimates tokens in message history
    2. MessageCompressor checks if compression is needed
    3. If threshold exceeded, older messages are summarized
    4. Summary replaces old messages, recent turns preserved

Usage:
    compressor = MessageCompressor()
    if compressor.should_compress(messages):
        messages = await compressor.compress(messages)
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

from agent.providers import get_haiku_model

if TYPE_CHECKING:
    pass


# Type alias for message list
Messages = list[ModelRequest | ModelResponse]


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class CompressionConfig:
    """Configuration for message compression."""

    # Maximum context tokens (Claude's limit is 200K)
    max_tokens: int = 200_000

    # Compress when usage exceeds this percentage of max_tokens
    # 65% = ~130K tokens triggers compression
    compress_threshold: float = 0.65

    # Number of recent conversation turns to preserve uncompressed
    # A "turn" is one user message + one assistant response
    keep_recent_turns: int = 4

    # Minimum messages required before compression is considered
    min_messages_for_compression: int = 10

    # Maximum length for the summary
    max_summary_tokens: int = 2000


# =============================================================================
# Token Counter
# =============================================================================

class TokenCounter:
    """
    Estimate token count for messages.

    Uses a simple character-based heuristic. For more accurate counting,
    consider using tiktoken or Anthropic's token counting API.
    """

    # Approximate characters per token for Claude models
    # This is a rough estimate - actual ratio varies by content
    CHARS_PER_TOKEN = 4

    def count(self, messages: Messages) -> int:
        """
        Count approximate tokens in a message list.

        Args:
            messages: List of ModelRequest/ModelResponse messages

        Returns:
            Estimated token count
        """
        total_chars = 0

        for msg in messages:
            if isinstance(msg, (ModelRequest, ModelResponse)):
                for part in msg.parts:
                    total_chars += self._count_part(part)

        return total_chars // self.CHARS_PER_TOKEN

    def _count_part(self, part) -> int:
        """Count characters in a message part."""
        if isinstance(part, TextPart):
            return len(part.content)
        elif isinstance(part, UserPromptPart):
            return len(part.content)
        elif isinstance(part, ToolCallPart):
            # Tool name + args
            args_str = str(part.args) if part.args else ""
            return len(part.tool_name) + len(args_str)
        elif isinstance(part, ToolReturnPart):
            content = part.content
            if isinstance(content, str):
                return len(content)
            return len(str(content))
        else:
            # Fallback for unknown parts
            return len(str(part))

    def count_text(self, text: str) -> int:
        """Count tokens in a plain text string."""
        return len(text) // self.CHARS_PER_TOKEN


# =============================================================================
# Compactor Agent
# =============================================================================

# System prompt for the compactor agent
COMPACTOR_SYSTEM_PROMPT = """You are a conversation summarizer. Your job is to create concise summaries of conversations between a user and an AI assistant working on LaTeX documents.

Rules:
1. Preserve key information: file names, specific edits made, errors encountered, solutions applied
2. Maintain chronological order of events
3. Be concise but complete - don't lose important context
4. Format as bullet points for clarity
5. Note any user preferences or patterns observed

CRITICAL: The summary is for CONTEXT ONLY, not a task list!
- Mark all actions as COMPLETED/DONE - they are history, not pending tasks
- Do NOT create a list that looks like pending work
- The AI should NOT try to continue or repeat these actions

Output format:
## Conversation Summary

### Project Context
[Brief description of the project/task]

### Completed Actions (DO NOT REPEAT)
- [DONE] Action 1
- [DONE] Action 2
...

### Current State
[What was accomplished - all tasks from this summary are COMPLETED]

### Reference Information
[File names, specific LaTeX packages, user preferences, etc.]

IMPORTANT: Everything in this summary is HISTORICAL. The assistant must NOT try to re-execute any of these actions.
"""


def _create_compactor_agent() -> Agent:
    """Create the compactor agent using Haiku model."""
    return Agent(
        model=get_haiku_model(),
        system_prompt=COMPACTOR_SYSTEM_PROMPT,
    )


# Lazy-loaded compactor agent
_compactor_agent: Agent | None = None


def get_compactor_agent() -> Agent:
    """Get or create the compactor agent."""
    global _compactor_agent
    if _compactor_agent is None:
        _compactor_agent = _create_compactor_agent()
    return _compactor_agent


# =============================================================================
# Message Compressor
# =============================================================================

@dataclass
class MessageCompressor:
    """
    Compresses message history when approaching context limits.

    The compressor:
    1. Monitors token usage in conversation history
    2. When threshold is exceeded, splits history into old/recent
    3. Summarizes old messages using a smaller model
    4. Returns compressed history with summary + recent messages
    """

    config: CompressionConfig = field(default_factory=CompressionConfig)
    counter: TokenCounter = field(default_factory=TokenCounter)

    def should_compress(self, messages: Messages) -> bool:
        """
        Check if compression is needed.

        Args:
            messages: Current message history

        Returns:
            True if compression should be performed
        """
        # Don't compress very short conversations
        if len(messages) < self.config.min_messages_for_compression:
            return False

        # Check token count
        tokens = self.counter.count(messages)
        threshold = int(self.config.max_tokens * self.config.compress_threshold)

        return tokens > threshold

    def get_compression_stats(self, messages: Messages) -> dict:
        """
        Get statistics about current compression state.

        Useful for debugging and monitoring.
        """
        tokens = self.counter.count(messages)
        threshold = int(self.config.max_tokens * self.config.compress_threshold)

        return {
            "message_count": len(messages),
            "estimated_tokens": tokens,
            "threshold_tokens": threshold,
            "max_tokens": self.config.max_tokens,
            "usage_percent": round(tokens / self.config.max_tokens * 100, 1),
            "should_compress": tokens > threshold,
        }

    async def compress(self, messages: Messages) -> Messages:
        """
        Compress message history by summarizing old messages.

        Args:
            messages: Full message history

        Returns:
            Compressed message history with summary + recent messages
        """
        # Calculate how many messages to keep
        # Each "turn" is roughly 2 messages (request + response)
        keep_count = self.config.keep_recent_turns * 2

        # If not enough messages to compress meaningfully, return as-is
        if len(messages) <= keep_count + 2:
            return messages

        # Split into old and recent
        old_messages = messages[:-keep_count]
        recent_messages = messages[-keep_count:]

        # Summarize old messages
        summary = await self._summarize(old_messages)

        # Create summary as a system-style context message
        summary_messages = self._create_summary_messages(summary)

        return summary_messages + recent_messages

    async def _summarize(self, messages: Messages) -> str:
        """
        Use compactor agent to summarize messages.

        Args:
            messages: Messages to summarize

        Returns:
            Summary text
        """
        # Format messages for summarization
        formatted = self._format_for_summary(messages)

        # Get compactor agent
        compactor = get_compactor_agent()

        # Run summarization
        prompt = f"""Summarize this conversation between a user and an AI assistant.
The conversation has {len(messages)} messages.

---
{formatted}
---

Create a concise summary following your instructions."""

        try:
            result = await compactor.run(prompt)
            return result.output or "Summary unavailable"
        except Exception as e:
            # Fallback to basic summary on error
            return f"[Compression error: {e}]\n\nPrevious conversation contained {len(messages)} messages."

    def _format_for_summary(self, messages: Messages) -> str:
        """
        Format messages as readable text for summarization.

        Args:
            messages: Messages to format

        Returns:
            Formatted conversation text
        """
        lines = []

        for msg in messages:
            if isinstance(msg, ModelRequest):
                # User messages and tool returns
                for part in msg.parts:
                    if isinstance(part, UserPromptPart):
                        lines.append(f"USER: {self._truncate(part.content, 500)}")
                    elif isinstance(part, ToolReturnPart):
                        content = str(part.content)[:200]
                        lines.append(f"TOOL RESULT ({part.tool_name}): {content}...")

            elif isinstance(msg, ModelResponse):
                # Assistant messages and tool calls
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        lines.append(f"ASSISTANT: {self._truncate(part.content, 500)}")
                    elif isinstance(part, ToolCallPart):
                        args_preview = str(part.args)[:100] if part.args else ""
                        lines.append(f"TOOL CALL: {part.tool_name}({args_preview}...)")

        return "\n\n".join(lines)

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis if too long."""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def _create_summary_messages(self, summary: str) -> Messages:
        """
        Create message objects containing the summary.

        The summary is injected as a user message followed by an
        acknowledgment from the assistant, maintaining valid
        message alternation.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        # Create summary as user context message
        # Note: ModelRequest doesn't have timestamp in newer PydanticAI versions
        summary_request = ModelRequest(
            parts=[
                UserPromptPart(
                    content=f"[CONVERSATION SUMMARY - Previous messages compressed]\n\n{summary}",
                    timestamp=now,
                )
            ],
        )

        # Create acknowledgment response
        ack_response = ModelResponse(
            parts=[
                TextPart(
                    content="I understand the historical context. I will NOT re-execute any actions from the summary - those are completed. I will wait for the user's new instructions.",
                )
            ],
            timestamp=now,
            model_name="compressor",
        )

        return [summary_request, ack_response]


# =============================================================================
# Convenience Functions
# =============================================================================

# Default compressor instance
_default_compressor: MessageCompressor | None = None


def get_compressor() -> MessageCompressor:
    """Get or create the default message compressor."""
    global _default_compressor
    if _default_compressor is None:
        _default_compressor = MessageCompressor()
    return _default_compressor


async def compress_if_needed(messages: Messages) -> tuple[Messages, bool]:
    """
    Compress messages if needed.

    Convenience function for use in streaming runner.

    Args:
        messages: Current message history

    Returns:
        Tuple of (possibly compressed messages, whether compression occurred)
    """
    compressor = get_compressor()

    if compressor.should_compress(messages):
        compressed = await compressor.compress(messages)
        return compressed, True

    return messages, False
