"""
Agent Tools Package

Modular tool system for the Aura agent.

Categories:
- file_tools: File operations (read, write, edit, list, find, search)
- latex_tools: LaTeX compilation, syntax checking, and content generation
- research_tools: PDF reading and subagent delegation
- planning_tools: Task planning and execution management
- writing_tools: Document structure analysis and citation management
- utility_tools: General utilities (think)
- memory_tools: Persistent memory for cross-session learning

Usage:
    from agent.tools import register_all_tools

    # Register all tools with an agent
    register_all_tools(agent, check_hitl_func=my_hitl_checker)
"""

from agent.tools.registry import (
    ToolRegistry,
    ToolDefinition,
    tool,
    get_registry,
    get_all_tools,
    get_enabled_tools,
    get_tools_by_category,
    get_tool,
)

from agent.tools.file_tools import register_file_tools
from agent.tools.latex_tools import register_latex_tools
from agent.tools.research_tools import register_research_tools
from agent.tools.planning_tools import register_planning_tools
from agent.tools.writing_tools import register_writing_tools
from agent.tools.utility_tools import register_utility_tools
from agent.tools.memory_tools import register_memory_tools


def register_all_tools(agent, check_hitl_func=None):
    """
    Register all tool categories with an agent.

    Args:
        agent: PydanticAI Agent instance
        check_hitl_func: HITL check function for dangerous operations
    """
    register_file_tools(agent, check_hitl_func)
    register_latex_tools(agent)
    register_research_tools(agent)
    register_planning_tools(agent)
    register_writing_tools(agent)
    register_utility_tools(agent)
    register_memory_tools(agent)


__all__ = [
    # Registry
    "ToolRegistry",
    "ToolDefinition",
    "tool",
    "get_registry",
    "get_all_tools",
    "get_enabled_tools",
    "get_tools_by_category",
    "get_tool",
    # Registration
    "register_all_tools",
    "register_file_tools",
    "register_latex_tools",
    "register_research_tools",
    "register_planning_tools",
    "register_writing_tools",
    "register_utility_tools",
    "register_memory_tools",
]
