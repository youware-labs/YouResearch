"""
Message Compression for Long Conversations

Automatically compresses old messages when approaching context limit.
Uses a smaller model (Haiku) to summarize conversation history.

Architecture:
    1. TokenCounter estimates tokens in message history (with tiktoken support)
    2. MessageCompressor checks if compression is needed
    3. If threshold exceeded, older messages are summarized
    4. Summary replaces old messages, recent turns preserved
    5. Compression results are cached for performance

Usage:
    compressor = MessageCompressor()
    if compressor.should_compress(messages):
        messages = await compressor.compress(messages)
"""

import hashlib
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

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

logger = logging.getLogger(__name__)


# Type alias for message list
Messages = list[ModelRequest | ModelResponse]

# Try to import tiktoken for accurate token counting
_tiktoken_encoder = None
_tiktoken_available = False

try:
    import tiktoken
    # Use cl100k_base which is used by Claude and GPT-4
    _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    _tiktoken_available = True
    logger.info("tiktoken available for accurate token counting")
except ImportError:
    logger.info("tiktoken not available, using character-based estimation")


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

    # Enable compression result caching
    enable_cache: bool = True

    # Maximum cache entries
    max_cache_entries: int = 100


# =============================================================================
# Token Counter
# =============================================================================

class TokenCounter:
    """
    Estimate token count for messages.

    Uses tiktoken for accurate counting if available, otherwise falls back
    to character-based heuristic.
    """

    # Approximate characters per token for Claude models (fallback)
    CHARS_PER_TOKEN = 4

    def __init__(self):
        self._use_tiktoken = _tiktoken_available
        self._encoder = _tiktoken_encoder

    @lru_cache(maxsize=1000)
    def _count_text_cached(self, text: str) -> int:
        """Count tokens in text with caching."""
        if self._use_tiktoken and self._encoder:
            return len(self._encoder.encode(text))
        return len(text) // self.CHARS_PER_TOKEN

    def count(self, messages: Messages) -> int:
        """
        Count approximate tokens in a message list.

        Args:
            messages: List of ModelRequest/ModelResponse messages

        Returns:
            Estimated token count
        """
        total_tokens = 0

        for msg in messages:
            if isinstance(msg, (ModelRequest, ModelResponse)):
                for part in msg.parts:
                    total_tokens += self._count_part(part)

        return total_tokens

    def _count_part(self, part) -> int:
        """Count tokens in a message part."""
        if isinstance(part, TextPart):
            return self._count_text_cached(part.content)
        elif isinstance(part, UserPromptPart):
            return self._count_text_cached(part.content)
        elif isinstance(part, ToolCallPart):
            # Tool name + args
            args_str = str(part.args) if part.args else ""
            text = part.tool_name + args_str
            return self._count_text_cached(text)
        elif isinstance(part, ToolReturnPart):
            content = part.content
            if isinstance(content, str):
                return self._count_text_cached(content)
            return self._count_text_cached(str(content))
        else:
            # Fallback for unknown parts
            return self._count_text_cached(str(part))

    def count_text(self, text: str) -> int:
        """Count tokens in a plain text string."""
        return self._count_text_cached(text)

    def clear_cache(self) -> None:
        """Clear the token counting cache."""
        self._count_text_cached.cache_clear()


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

# Cache for compression results (message hash -> summary)
_compression_cache: dict[str, str] = {}


def _compute_messages_hash(messages: Messages) -> str:
    """Compute a hash for a list of messages for caching."""
    content_parts = []
    for msg in messages:
        if isinstance(msg, (ModelRequest, ModelResponse)):
            for part in msg.parts:
                if isinstance(part, (TextPart, UserPromptPart)):
                    content_parts.append(part.content[:100])  # Use first 100 chars
                elif isinstance(part, ToolCallPart):
                    content_parts.append(f"{part.tool_name}:{part.tool_call_id}")
    content = "|".join(content_parts)
    return hashlib.md5(content.encode()).hexdigest()


@dataclass
class MessageCompressor:
    """
    Compresses message history when approaching context limits.

    The compressor:
    1. Monitors token usage in conversation history
    2. When threshold is exceeded, splits history into old/recent
    3. Summarizes old messages using a smaller model
    4. Returns compressed history with summary + recent messages
    5. Caches compression results for performance

    Features:
    - tiktoken-based accurate token counting (with fallback)
    - Compression result caching
    - Graceful fallback on compression failure
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
            "using_tiktoken": self.counter._use_tiktoken,
            "cache_size": len(_compression_cache),
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

        # Try to get cached summary
        summary: Optional[str] = None
        cache_key: Optional[str] = None

        if self.config.enable_cache:
            cache_key = _compute_messages_hash(old_messages)
            summary = _compression_cache.get(cache_key)
            if summary:
                logger.debug(f"Using cached compression result (key: {cache_key[:8]})")

        # Summarize old messages if not cached
        if summary is None:
            summary = await self._summarize_with_fallback(old_messages)

            # Cache the result
            if self.config.enable_cache and cache_key:
                # Limit cache size
                if len(_compression_cache) >= self.config.max_cache_entries:
                    # Remove oldest entry (FIFO)
                    oldest_key = next(iter(_compression_cache))
                    del _compression_cache[oldest_key]
                _compression_cache[cache_key] = summary

        # Create summary as a system-style context message
        summary_messages = self._create_summary_messages(summary)

        return summary_messages + recent_messages

    async def _summarize_with_fallback(self, messages: Messages) -> str:
        """
        Summarize messages with multiple fallback strategies.

        Args:
            messages: Messages to summarize

        Returns:
            Summary text (always returns something, never raises)
        """
        # Strategy 1: Try LLM-based summarization
        try:
            summary = await self._summarize(messages)
            if summary and len(summary) > 50:  # Valid summary
                return summary
        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}")

        # Strategy 2: Extractive summary (take key excerpts)
        try:
            summary = self._extractive_summary(messages)
            if summary:
                return summary
        except Exception as e:
            logger.warning(f"Extractive summary failed: {e}")

        # Strategy 3: Basic fallback (just message count)
        return self._basic_fallback_summary(messages)

    def _extractive_summary(self, messages: Messages) -> str:
        """
        Create an extractive summary by selecting key message excerpts.

        Used as fallback when LLM summarization fails.
        """
        user_messages = []
        assistant_messages = []
        tool_calls = []

        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart):
                        user_messages.append(self._truncate(part.content, 200))
            elif isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        assistant_messages.append(self._truncate(part.content, 200))
                    elif isinstance(part, ToolCallPart):
                        tool_calls.append(part.tool_name)

        lines = [
            "## Conversation Summary (Extractive)",
            "",
            "### User Requests",
        ]

        # Include first and last few user messages
        for msg in user_messages[:2] + user_messages[-2:]:
            lines.append(f"- {msg}")

        if tool_calls:
            lines.extend([
                "",
                "### Tools Used",
                f"- {', '.join(set(tool_calls))}",
            ])

        if assistant_messages:
            lines.extend([
                "",
                "### Key Responses",
            ])
            for msg in assistant_messages[-2:]:  # Last 2 responses
                lines.append(f"- {msg}")

        lines.extend([
            "",
            f"(Total: {len(messages)} messages compressed)",
        ])

        return "\n".join(lines)

    def _basic_fallback_summary(self, messages: Messages) -> str:
        """
        Create a basic fallback summary when all else fails.
        """
        return f"""## Conversation Summary (Basic)

Previous conversation contained {len(messages)} messages.
Context may be incomplete due to compression error.

Please continue from the recent messages below."""

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

        result = await compactor.run(prompt)
        return result.output or "Summary unavailable"

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
