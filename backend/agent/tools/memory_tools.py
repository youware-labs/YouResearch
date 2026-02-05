"""
Memory Tools

Tools for persistent memory management across sessions.
Enables cross-session learning and context persistence.
"""

from pydantic_ai import Agent, RunContext

from agent.logging import get_logger, log_tool_call, log_tool_success, log_tool_error
from agent.errors import ToolError, ErrorCode

logger = get_logger("tools.memory")

# Memory configuration
MEMORY_MAX_LINES = 200


def register_memory_tools(agent: Agent, **kwargs) -> None:
    """Register memory tools with the agent."""

    @agent.tool
    async def read_project_memory(ctx: RunContext) -> str:
        """
        Read the project's persistent memory (MEMORY.md).

        This file contains learnings, patterns, preferences, and key decisions
        from previous sessions. Use this to understand project context.

        Returns:
            Content of MEMORY.md or message if empty
        """
        from services.persistent_memory import get_persistent_memory

        log_tool_call(logger, "read_project_memory")

        memory_service = get_persistent_memory(ctx.deps.project_path)
        content = memory_service.read_memory()

        if not content:
            log_tool_success(logger, "read_project_memory", status="empty")
            return "MEMORY.md is empty. You can write learnings and patterns using update_project_memory."

        log_tool_success(logger, "read_project_memory", lines=content.count("\n") + 1)
        return f"# Project Memory (MEMORY.md)\n\n{content}"

    @agent.tool
    async def update_project_memory(
        ctx: RunContext,
        section: str,
        content: str,
    ) -> str:
        """
        Add content to the project's persistent memory.

        Use this to record learnings, patterns, conventions, or key decisions
        that should be remembered across sessions.

        Args:
            section: Section header (e.g., "## Learnings", "## Conventions", "## Key Decisions")
            content: Content to add under the section (use markdown formatting)

        Returns:
            Confirmation message

        Example:
            section: "## Conventions"
            content: "- Always use \\citep{} for parenthetical citations, not \\cite{}"
        """
        from services.persistent_memory import get_persistent_memory

        log_tool_call(logger, "update_project_memory", section=section)

        # Validate section format
        if not section.startswith("## "):
            section = f"## {section}"

        memory_service = get_persistent_memory(ctx.deps.project_path)
        success = memory_service.append_to_memory(section, content)

        if success:
            stats = memory_service.get_stats()
            log_tool_success(logger, "update_project_memory", section=section)

            result = f"Added to {section} in MEMORY.md"
            if stats.warning:
                result += f"\n\n⚠️ Warning: {stats.warning_message}"
            return result
        else:
            log_tool_error(logger, "update_project_memory", "WRITE_FAILED", "Failed to update memory")
            raise ToolError(ErrorCode.INTERNAL_ERROR, "Failed to update project memory")

    @agent.tool
    async def get_memory_stats(ctx: RunContext) -> str:
        """
        Get statistics about project memory usage.

        Returns:
            Memory statistics including line count, token usage, and session summaries
        """
        from services.persistent_memory import get_persistent_memory

        log_tool_call(logger, "get_memory_stats")

        memory_service = get_persistent_memory(ctx.deps.project_path)
        stats = memory_service.get_stats()

        log_tool_success(logger, "get_memory_stats")

        return f"""# Memory Statistics

**MEMORY.md:**
- Lines: {stats.memory_md_lines} / {MEMORY_MAX_LINES} max
- Estimated tokens: {stats.memory_md_tokens}

**Session Summaries:**
- Count: {stats.session_summary_count}

**Token Budget:**
- Used: {stats.used_tokens} / {stats.total_token_budget}

{f"⚠️ Warning: {stats.warning_message}" if stats.warning else "✓ Memory usage is healthy"}
"""
