"""
Tool Registry System

Provides a centralized registry for agent tools with:
- Automatic tool registration via decorators
- Category-based organization
- Dynamic tool loading/filtering
- Tool metadata management

Usage:
    from agent.tools.registry import tool, get_all_tools

    @tool(category="file", description="Read a file")
    async def read_file(ctx: RunContext[AuraDeps], filepath: str) -> str:
        ...

    # Get all tools for an agent
    tools = get_all_tools()
    for t in tools:
        agent.tool(t.handler)
"""

from dataclasses import dataclass, field
from typing import Callable, Any, TypeVar, ParamSpec
from functools import wraps

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class ToolDefinition:
    """Metadata and handler for a registered tool."""
    name: str
    category: str
    description: str
    handler: Callable
    requires_hitl: bool = False  # Whether this tool needs HITL approval
    enabled: bool = True


class ToolRegistry:
    """
    Singleton registry for all agent tools.

    Tools are registered via the @tool decorator and can be
    filtered by category or enabled/disabled dynamically.
    """
    _instance: "ToolRegistry | None" = None
    _tools: dict[str, ToolDefinition]

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(
        self,
        name: str,
        category: str,
        description: str = "",
        requires_hitl: bool = False,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """
        Decorator to register a tool.

        Args:
            name: Tool name (should match function name)
            category: Category for grouping (file, latex, research, etc.)
            description: Human-readable description
            requires_hitl: Whether tool needs human approval

        Returns:
            Decorator function
        """
        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            self._tools[name] = ToolDefinition(
                name=name,
                category=category,
                description=description or func.__doc__ or "",
                handler=func,
                requires_hitl=requires_hitl,
            )
            return func
        return decorator

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[ToolDefinition]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_by_category(self, category: str) -> list[ToolDefinition]:
        """Get all tools in a category."""
        return [t for t in self._tools.values() if t.category == category]

    def get_enabled(self) -> list[ToolDefinition]:
        """Get all enabled tools."""
        return [t for t in self._tools.values() if t.enabled]

    def enable(self, name: str) -> bool:
        """Enable a tool. Returns True if found."""
        if name in self._tools:
            self._tools[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a tool. Returns True if found."""
        if name in self._tools:
            self._tools[name].enabled = False
            return True
        return False

    def enable_category(self, category: str) -> int:
        """Enable all tools in a category. Returns count."""
        count = 0
        for tool in self._tools.values():
            if tool.category == category:
                tool.enabled = True
                count += 1
        return count

    def disable_category(self, category: str) -> int:
        """Disable all tools in a category. Returns count."""
        count = 0
        for tool in self._tools.values():
            if tool.category == category:
                tool.enabled = False
                count += 1
        return count

    def list_categories(self) -> list[str]:
        """Get all unique categories."""
        return list(set(t.category for t in self._tools.values()))

    def clear(self) -> None:
        """Clear all registered tools (useful for testing)."""
        self._tools.clear()


# =============================================================================
# Module-level convenience functions
# =============================================================================

_registry = ToolRegistry()


def tool(
    category: str,
    name: str | None = None,
    description: str = "",
    requires_hitl: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to register a tool with the global registry.

    Args:
        category: Category for grouping (file, latex, research, etc.)
        name: Tool name (defaults to function name)
        description: Human-readable description (defaults to docstring)
        requires_hitl: Whether tool needs human approval

    Example:
        @tool(category="file", requires_hitl=True)
        async def edit_file(ctx, filepath: str, old: str, new: str) -> str:
            '''Edit a file by replacing text.'''
            ...
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        tool_name = name or func.__name__
        return _registry.register(
            name=tool_name,
            category=category,
            description=description,
            requires_hitl=requires_hitl,
        )(func)
    return decorator


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return _registry


def get_all_tools() -> list[ToolDefinition]:
    """Get all registered tools."""
    return _registry.get_all()


def get_enabled_tools() -> list[ToolDefinition]:
    """Get all enabled tools."""
    return _registry.get_enabled()


def get_tools_by_category(category: str) -> list[ToolDefinition]:
    """Get all tools in a category."""
    return _registry.get_by_category(category)


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool by name."""
    return _registry.get(name)
