"""
Subagent Base Classes

Base infrastructure for specialized subagents that handle specific tasks.
Subagents are focused agents with limited tool sets for specific domains.

Architecture:
    Main Agent (aura_agent)
         │
         ├─> delegate_to_subagent("research", "Find papers on transformers")
         │        │
         │        └─> ResearchAgent
         │               ├─ search_arxiv
         │               ├─ search_semantic_scholar
         │               └─ summarize_paper
         │
         └─> delegate_to_subagent("compiler", "Fix LaTeX error")
                  │
                  └─> CompilerAgent
                         ├─ read_file
                         ├─ edit_file
                         └─ compile_and_check

Usage:
    from agent.subagents import get_subagent, run_subagent

    # Get a subagent by name
    agent = get_subagent("research")

    # Run with task
    result = await run_subagent("research", "Find recent papers on LLMs")
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic_ai import Agent

from agent.providers import get_default_model, get_haiku_model

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SubagentConfig:
    """
    Configuration for a subagent.

    Attributes:
        name: Unique identifier for the subagent
        description: Human-readable description of what this subagent does
        model: Model to use (default: same as main agent)
        max_iterations: Maximum tool call iterations (prevents infinite loops)
        timeout: Maximum execution time in seconds
        use_haiku: If True, use cheaper Haiku model instead of Sonnet
    """
    name: str
    description: str = ""
    model: str = "anthropic:claude-4-5-sonnet-by-all"
    max_iterations: int = 15
    timeout: float = 120.0  # 2 minutes default
    use_haiku: bool = False  # Use cheaper model for simple tasks


@dataclass
class SubagentResult:
    """
    Result from a subagent execution.

    Contains the output plus metadata about the execution.
    """
    # Primary output
    output: str

    # Execution metadata
    subagent_name: str
    task: str
    success: bool = True
    error: str | None = None

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float = 0.0

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "output": self.output,
            "subagent_name": self.subagent_name,
            "task": self.task,
            "success": self.success,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


# =============================================================================
# Base Subagent Class
# =============================================================================

DepsT = TypeVar("DepsT")


class Subagent(ABC, Generic[DepsT]):
    """
    Abstract base class for specialized subagents.

    Subagents are focused agents with a specific purpose and limited tool set.
    They inherit from this class and implement:
    - _create_agent(): Creates the PydanticAI agent with tools
    - system_prompt: The specialized system prompt

    Example:
        class ResearchAgent(Subagent[ResearchDeps]):
            @property
            def system_prompt(self) -> str:
                return "You are a research assistant..."

            def _create_agent(self) -> Agent[ResearchDeps, str]:
                agent = Agent(
                    model=self._get_model(),
                    system_prompt=self.system_prompt,
                    deps_type=ResearchDeps,
                )

                @agent.tool
                async def search_arxiv(...):
                    ...

                return agent
    """

    def __init__(self, config: SubagentConfig):
        """
        Initialize the subagent.

        Args:
            config: Subagent configuration
        """
        self.config = config
        self._agent: Agent | None = None

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt for this subagent."""
        pass

    @abstractmethod
    def _create_agent(self) -> Agent:
        """
        Create the PydanticAI agent with appropriate tools.

        This method should:
        1. Create an Agent with the model and system prompt
        2. Register any specialized tools using @agent.tool
        3. Return the configured agent

        Returns:
            Configured PydanticAI Agent
        """
        pass

    @abstractmethod
    def _create_deps(self, context: dict[str, Any]) -> DepsT:
        """
        Create dependencies for agent execution.

        Args:
            context: Context dictionary passed from main agent

        Returns:
            Dependencies object for the agent
        """
        pass

    def _get_model(self):
        """Get the appropriate model for this subagent."""
        if self.config.use_haiku:
            return get_haiku_model()
        return get_default_model()

    @property
    def agent(self) -> Agent:
        """Lazily create and return the agent."""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    async def run(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> SubagentResult:
        """
        Run the subagent on a task.

        Args:
            task: The task to perform
            context: Optional context dictionary (e.g., project_path)

        Returns:
            SubagentResult with output and metadata
        """
        context = context or {}
        started_at = datetime.now(timezone.utc)

        logger.info(f"Subagent '{self.config.name}' starting task: {task[:100]}...")

        # Retry logic for rate limits
        max_retries = 3
        retry_delay = 5.0  # Start with 5 seconds

        for attempt in range(max_retries + 1):
            try:
                # Apply timeout
                async with asyncio.timeout(self.config.timeout):
                    deps = self._create_deps(context)
                    result = await self.agent.run(task, deps=deps)

                completed_at = datetime.now(timezone.utc)
                duration = (completed_at - started_at).total_seconds()

                # Extract usage
                usage = result.usage()

                logger.info(
                    f"Subagent '{self.config.name}' completed in {duration:.1f}s "
                    f"({usage.input_tokens}in/{usage.output_tokens}out tokens)"
                )

                return SubagentResult(
                    output=result.output or "",
                    subagent_name=self.config.name,
                    task=task,
                    success=True,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration,
                    input_tokens=usage.input_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0,
                )

            except asyncio.TimeoutError:
                logger.error(f"Subagent '{self.config.name}' timed out after {self.config.timeout}s")
                return SubagentResult(
                    output=f"Error: Task timed out after {self.config.timeout} seconds",
                    subagent_name=self.config.name,
                    task=task,
                    success=False,
                    error="timeout",
                    started_at=started_at,
                )

            except Exception as e:
                error_str = str(e)
                # Check for rate limit error (429)
                if "429" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries:
                        logger.warning(
                            f"Subagent '{self.config.name}' hit rate limit, "
                            f"retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue

                logger.error(f"Subagent '{self.config.name}' failed: {e}")
                return SubagentResult(
                    output=f"Error: {str(e)}",
                    subagent_name=self.config.name,
                    task=task,
                    success=False,
                    error=str(e),
                    started_at=started_at,
                )

        # Should not reach here, but just in case
        return SubagentResult(
            output="Error: Max retries exceeded",
            subagent_name=self.config.name,
            task=task,
            success=False,
            error="max_retries",
            started_at=started_at,
        )


# =============================================================================
# Subagent Registry
# =============================================================================

_subagent_registry: dict[str, type[Subagent]] = {}


def register_subagent(name: str):
    """
    Decorator to register a subagent class.

    Usage:
        @register_subagent("research")
        class ResearchAgent(Subagent):
            ...
    """
    def decorator(cls: type[Subagent]) -> type[Subagent]:
        _subagent_registry[name] = cls
        logger.debug(f"Registered subagent: {name}")
        return cls
    return decorator


def get_subagent(name: str, **kwargs) -> Subagent:
    """
    Get a subagent instance by name.

    Args:
        name: Name of the registered subagent
        **kwargs: Additional arguments passed to subagent constructor

    Returns:
        Instantiated subagent

    Raises:
        KeyError: If subagent name is not registered
    """
    if name not in _subagent_registry:
        available = ", ".join(_subagent_registry.keys()) or "none"
        raise KeyError(f"Unknown subagent: '{name}'. Available: {available}")

    cls = _subagent_registry[name]
    return cls(**kwargs)


def list_subagents() -> list[dict[str, str]]:
    """
    List all registered subagents.

    Returns:
        List of dicts with name and description
    """
    result = []
    for name, cls in _subagent_registry.items():
        # Instantiate to get description
        try:
            instance = cls()
            result.append({
                "name": name,
                "description": instance.config.description,
            })
        except Exception:
            result.append({
                "name": name,
                "description": "(failed to load)",
            })
    return result


async def run_subagent(
    name: str,
    task: str,
    context: dict[str, Any] | None = None,
    **kwargs,
) -> SubagentResult:
    """
    Convenience function to run a subagent by name.

    Args:
        name: Subagent name
        task: Task to perform
        context: Optional context dictionary
        **kwargs: Additional arguments for subagent constructor

    Returns:
        SubagentResult from the subagent
    """
    subagent = get_subagent(name, **kwargs)
    return await subagent.run(task, context)
