"""
Tool Manager

Pluggy-based auto-discovery and registration of agent tools.
"""

import pluggy
from pathlib import Path
from importlib import import_module
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)

PROJECT_NAME = "aura"

# Pluggy markers
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class ToolSpec:
    """Hook specifications for tool registration."""

    @hookspec
    def register_tools(self) -> list[dict]:
        """
        Return list of tool definitions.

        Each tool should be a dict with:
        - name: str - Tool name
        - description: str - Tool description for the LLM
        - function: Callable - The async function to execute
        - parameters: dict - JSON schema for parameters
        """


class ToolDefinition:
    """
    A tool that can be used by the agent.

    Wraps a function with metadata for the LLM.
    """

    def __init__(
        self,
        name: str,
        description: str,
        function: Callable,
        parameters: dict[str, Any],
    ):
        self.name = name
        self.description = description
        self.function = function
        self.parameters = parameters

    def to_anthropic_tool(self) -> dict:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
        }

    async def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments."""
        import asyncio

        if asyncio.iscoroutinefunction(self.function):
            return await self.function(**kwargs)
        else:
            # Run sync functions in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: self.function(**kwargs))


class ToolManager:
    """
    Manages tool discovery and registration.

    Auto-discovers tools from backend/tools/*/*.py modules.
    Each module can register tools using the @hookimpl decorator.
    """

    def __init__(self):
        self.pm = pluggy.PluginManager(PROJECT_NAME)
        self.pm.add_hookspecs(ToolSpec)
        self._tools: dict[str, ToolDefinition] = {}
        self._discover_tools()

    def _discover_tools(self):
        """Auto-discover tools from backend/tools/*/."""
        tools_dir = Path(__file__).parent

        for subdir in tools_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                for py_file in subdir.glob("*.py"):
                    if py_file.name.startswith("_"):
                        continue

                    module_path = f"backend.tools.{subdir.name}.{py_file.stem}"
                    try:
                        module = import_module(module_path)
                        if hasattr(module, "register_tools"):
                            self.pm.register(module)
                            logger.info(f"Registered tools from {module_path}")
                    except Exception as e:
                        logger.warning(f"Failed to load {module_path}: {e}")

        # Collect all registered tools
        self._collect_tools()

    def _collect_tools(self):
        """Collect tools from all registered plugins."""
        for result in self.pm.hook.register_tools():
            if result:
                for tool_def in result:
                    if isinstance(tool_def, ToolDefinition):
                        self._tools[tool_def.name] = tool_def
                    elif isinstance(tool_def, dict):
                        # Support dict format for simpler registration
                        tool = ToolDefinition(
                            name=tool_def["name"],
                            description=tool_def["description"],
                            function=tool_def["function"],
                            parameters=tool_def.get("parameters", {}),
                        )
                        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> list[ToolDefinition]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_anthropic_tools(self) -> list[dict]:
        """Get all tools in Anthropic API format."""
        return [tool.to_anthropic_tool() for tool in self._tools.values()]

    async def execute_tool(self, name: str, **kwargs) -> str:
        """Execute a tool by name."""
        tool = self.get_tool(name)
        if not tool:
            return f"Error: Tool '{name}' not found"

        try:
            result = await tool.execute(**kwargs)
            return str(result) if result is not None else "Done"
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return f"Error executing {name}: {str(e)}"

    def list_tools(self) -> list[str]:
        """List all tool names."""
        return list(self._tools.keys())


# Global tool manager instance
_manager: ToolManager | None = None


def get_tool_manager() -> ToolManager:
    """Get or create the global tool manager."""
    global _manager
    if _manager is None:
        _manager = ToolManager()
    return _manager


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
):
    """
    Decorator to create a tool from a function.

    Usage:
        @tool("read_file", "Read a file", {"properties": {...}})
        async def read_file(path: str) -> str:
            ...
    """
    def decorator(func: Callable) -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description=description,
            function=func,
            parameters=parameters or {},
        )
    return decorator
