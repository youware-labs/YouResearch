"""
Persistent Memory Service

File-based memory system for cross-session learning and context persistence.
Inspired by Claude Code's CLAUDE.md approach.

Architecture:
    1. MEMORY.md - Agent-writable markdown file for learnings and preferences
    2. Session summaries - Compressed summaries of past conversations
    3. Context injection - Memory loaded into system prompt

Files stored in {project_path}/.aura/:
    - MEMORY.md: Agent learnings, patterns, preferences
    - session_summaries.json: Compressed summaries of past sessions
    - context_cache.json: Frequently accessed context (LRU cache)
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

from agent.logging import get_logger

logger = get_logger("persistent_memory")


# =============================================================================
# Configuration
# =============================================================================

# Maximum lines in MEMORY.md before warning
MEMORY_MAX_LINES = 200

# Maximum session summaries to keep
MAX_SESSION_SUMMARIES = 50

# Token budget for memory injection into prompt
MEMORY_TOKEN_BUDGET = 2000

# Chars per token estimate
CHARS_PER_TOKEN = 4


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SessionSummary:
    """Compressed summary of a completed session."""
    session_id: str
    created_at: str
    summary: str
    key_decisions: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    token_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionSummary":
        return cls(**data)


@dataclass
class MemoryStats:
    """Statistics about memory usage."""
    memory_md_lines: int
    memory_md_tokens: int
    session_summary_count: int
    total_token_budget: int
    used_tokens: int
    warning: bool = False
    warning_message: str = ""


# =============================================================================
# Persistent Memory Service
# =============================================================================

class PersistentMemoryService:
    """
    Manages persistent, file-based memory for agent learning.

    This enables:
    - Cross-session context (agent remembers past decisions)
    - Project-specific learnings (preferences, patterns)
    - Efficient context injection (summarized, not full history)
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.aura_dir = self.project_path / ".aura"
        self.memory_file = self.aura_dir / "MEMORY.md"
        self.summaries_file = self.aura_dir / "session_summaries.json"
        self.cache_file = self.aura_dir / "context_cache.json"

    def _ensure_aura_dir(self) -> None:
        """Ensure .aura directory exists."""
        self.aura_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # MEMORY.md Operations
    # -------------------------------------------------------------------------

    def read_memory(self) -> str:
        """
        Read the MEMORY.md file.

        Returns:
            Content of MEMORY.md, or empty string if not exists
        """
        if not self.memory_file.exists():
            return ""

        try:
            content = self.memory_file.read_text()
            logger.info("memory_read", lines=content.count("\n") + 1)
            return content
        except Exception as e:
            logger.error("memory_read_failed", error=str(e))
            return ""

    def write_memory(self, content: str) -> bool:
        """
        Write to MEMORY.md file.

        Args:
            content: Full content to write

        Returns:
            True if successful
        """
        self._ensure_aura_dir()

        try:
            # Check line count warning
            lines = content.count("\n") + 1
            if lines > MEMORY_MAX_LINES:
                logger.warning(
                    "memory_too_long",
                    lines=lines,
                    max_lines=MEMORY_MAX_LINES,
                    hint="Consider moving details to separate files in .aura/"
                )

            self.memory_file.write_text(content)
            logger.info("memory_written", lines=lines)
            return True
        except Exception as e:
            logger.error("memory_write_failed", error=str(e))
            return False

    def append_to_memory(self, section: str, content: str) -> bool:
        """
        Append content to a section in MEMORY.md.

        Args:
            section: Section header (e.g., "## Learnings")
            content: Content to append under the section

        Returns:
            True if successful
        """
        current = self.read_memory()

        if section in current:
            # Find the section and append after it
            parts = current.split(section, 1)
            if len(parts) == 2:
                # Find next section or end
                rest = parts[1]
                next_section_idx = rest.find("\n## ")
                if next_section_idx == -1:
                    # No next section, append at end
                    new_content = current.rstrip() + "\n" + content + "\n"
                else:
                    # Insert before next section
                    before_next = rest[:next_section_idx].rstrip()
                    after_next = rest[next_section_idx:]
                    new_content = parts[0] + section + before_next + "\n" + content + after_next
            else:
                new_content = current.rstrip() + "\n" + content + "\n"
        else:
            # Section doesn't exist, create it
            new_content = current.rstrip() + f"\n\n{section}\n\n{content}\n"

        return self.write_memory(new_content)

    def get_memory_for_prompt(self) -> str:
        """
        Get memory content formatted for system prompt injection.

        Returns:
            Formatted memory content, truncated to token budget
        """
        content = self.read_memory()
        if not content:
            return ""

        # Truncate if too long
        max_chars = MEMORY_TOKEN_BUDGET * CHARS_PER_TOKEN
        if len(content) > max_chars:
            # Truncate at line boundary
            lines = content.split("\n")
            truncated_lines = []
            char_count = 0
            for line in lines:
                if char_count + len(line) > max_chars:
                    truncated_lines.append("... (truncated, see MEMORY.md for full content)")
                    break
                truncated_lines.append(line)
                char_count += len(line) + 1
            content = "\n".join(truncated_lines)

        return f"## Project Memory (MEMORY.md)\n\n{content}"

    # -------------------------------------------------------------------------
    # Session Summary Operations
    # -------------------------------------------------------------------------

    def _load_summaries(self) -> list[dict]:
        """Load session summaries from disk."""
        if not self.summaries_file.exists():
            return []

        try:
            data = json.loads(self.summaries_file.read_text())
            return data.get("summaries", [])
        except Exception as e:
            logger.error("summaries_load_failed", error=str(e))
            return []

    def _save_summaries(self, summaries: list[dict]) -> None:
        """Save session summaries to disk."""
        self._ensure_aura_dir()

        # Prune old summaries
        if len(summaries) > MAX_SESSION_SUMMARIES:
            summaries = summaries[-MAX_SESSION_SUMMARIES:]

        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "summaries": summaries,
        }

        self.summaries_file.write_text(json.dumps(data, indent=2))

    def add_session_summary(self, summary: SessionSummary) -> None:
        """
        Add a session summary to persistent storage.

        Args:
            summary: SessionSummary object
        """
        summaries = self._load_summaries()

        # Check for duplicate
        for i, s in enumerate(summaries):
            if s.get("session_id") == summary.session_id:
                summaries[i] = summary.to_dict()
                self._save_summaries(summaries)
                logger.info("session_summary_updated", session_id=summary.session_id)
                return

        summaries.append(summary.to_dict())
        self._save_summaries(summaries)
        logger.info("session_summary_added", session_id=summary.session_id)

    def get_recent_summaries(self, count: int = 5) -> list[SessionSummary]:
        """
        Get recent session summaries.

        Args:
            count: Number of summaries to return

        Returns:
            List of SessionSummary objects, most recent first
        """
        summaries = self._load_summaries()
        recent = summaries[-count:] if count < len(summaries) else summaries
        return [SessionSummary.from_dict(s) for s in reversed(recent)]

    def get_summaries_for_prompt(self, count: int = 3) -> str:
        """
        Get session summaries formatted for prompt injection.

        Args:
            count: Number of recent summaries to include

        Returns:
            Formatted summary text
        """
        summaries = self.get_recent_summaries(count)
        if not summaries:
            return ""

        lines = ["## Recent Session Context\n"]
        for s in summaries:
            lines.append(f"### Session {s.session_id} ({s.created_at[:10]})")
            lines.append(s.summary)
            if s.key_decisions:
                lines.append("Key decisions:")
                for d in s.key_decisions[:3]:  # Limit to 3 decisions
                    lines.append(f"  - {d}")
            lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> MemoryStats:
        """Get memory usage statistics."""
        memory_content = self.read_memory()
        memory_lines = memory_content.count("\n") + 1 if memory_content else 0
        memory_tokens = len(memory_content) // CHARS_PER_TOKEN

        summaries = self._load_summaries()

        stats = MemoryStats(
            memory_md_lines=memory_lines,
            memory_md_tokens=memory_tokens,
            session_summary_count=len(summaries),
            total_token_budget=MEMORY_TOKEN_BUDGET,
            used_tokens=memory_tokens,
        )

        if memory_lines > MEMORY_MAX_LINES:
            stats.warning = True
            stats.warning_message = f"MEMORY.md has {memory_lines} lines (max: {MEMORY_MAX_LINES}). Consider moving details to separate files."

        return stats

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def initialize_memory(self) -> None:
        """
        Initialize MEMORY.md with default template if it doesn't exist.
        """
        if self.memory_file.exists():
            return

        template = """# Project Memory

This file stores learnings, patterns, and preferences discovered during our conversations.
The agent reads this file at the start of each session and can update it with new insights.

## Project Context

<!-- Add project-specific context here -->

## Conventions

<!-- Coding/writing conventions discovered -->

## Key Decisions

<!-- Important decisions made during development -->

## Learnings

<!-- Patterns, gotchas, and insights -->
"""

        self.write_memory(template)
        logger.info("memory_initialized", project=self.project_path.name)


# =============================================================================
# Session Summary Generator
# =============================================================================

async def generate_session_summary(
    session_id: str,
    messages: list,
    files_modified: list[str],
    tools_used: list[str],
) -> SessionSummary:
    """
    Generate a compressed summary of a session using the LLM.

    Args:
        session_id: Session identifier
        messages: PydanticAI message history
        files_modified: List of files modified during session
        tools_used: List of tools used during session

    Returns:
        SessionSummary object
    """
    from pydantic_ai import Agent
    from agent.providers import get_haiku_model

    # Extract text content from messages for summarization
    text_parts = []
    for msg in messages:
        if hasattr(msg, "parts"):
            for part in msg.parts:
                if hasattr(part, "content"):
                    content = part.content
                    if isinstance(content, str) and len(content) < 2000:
                        text_parts.append(content[:500])  # Truncate long parts

    conversation_text = "\n---\n".join(text_parts[-10:])  # Last 10 parts

    # Create summarization prompt
    prompt = f"""Summarize this conversation in 2-3 sentences. Focus on:
1. What was the main task/goal?
2. What was accomplished?
3. Any important decisions made?

Conversation:
{conversation_text}

Also extract 1-3 key decisions as bullet points (if any).
Format:
SUMMARY: <2-3 sentence summary>
DECISIONS:
- <decision 1>
- <decision 2>
"""

    try:
        # Use Haiku for cheap summarization
        summarizer = Agent(
            model=get_haiku_model(),
            result_type=str,
        )
        result = await summarizer.run(prompt)
        response = result.data

        # Parse response
        summary = ""
        decisions = []

        if "SUMMARY:" in response:
            summary_part = response.split("SUMMARY:")[1]
            if "DECISIONS:" in summary_part:
                summary = summary_part.split("DECISIONS:")[0].strip()
                decisions_part = summary_part.split("DECISIONS:")[1]
                for line in decisions_part.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        decisions.append(line[2:])
            else:
                summary = summary_part.strip()
        else:
            summary = response[:500]

        return SessionSummary(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            summary=summary,
            key_decisions=decisions,
            files_modified=files_modified,
            tools_used=list(set(tools_used)),
            token_count=len(response) // CHARS_PER_TOKEN,
        )

    except Exception as e:
        logger.error("summary_generation_failed", error=str(e))
        # Fallback to basic summary
        return SessionSummary(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            summary=f"Session with {len(messages)} messages. Files modified: {', '.join(files_modified[:5]) if files_modified else 'none'}",
            key_decisions=[],
            files_modified=files_modified,
            tools_used=list(set(tools_used)),
            token_count=0,
        )


# =============================================================================
# Singleton Access
# =============================================================================

_memory_services: dict[str, PersistentMemoryService] = {}


def get_persistent_memory(project_path: str) -> PersistentMemoryService:
    """
    Get or create a PersistentMemoryService for a project.

    Args:
        project_path: Path to the project

    Returns:
        PersistentMemoryService instance
    """
    if project_path not in _memory_services:
        _memory_services[project_path] = PersistentMemoryService(project_path)
    return _memory_services[project_path]
