"""
Subagents Module

Specialized agents that handle specific domain tasks.
The main agent delegates to these subagents for focused work.

Available Subagents:
    - research: Search arXiv and Semantic Scholar for papers
    - compiler: Fix LaTeX compilation errors
    - planner: Create structured plans for complex tasks
    - writing: Style analysis, consistency checking, bibliography management

Usage:
    from agent.subagents import get_subagent, run_subagent, list_subagents

    # List available subagents
    available = list_subagents()

    # Run a subagent directly
    result = await run_subagent(
        "research",
        "Find recent papers on large language models",
    )

    # Or get a subagent instance
    agent = get_subagent("compiler", project_path="/path/to/project")
    result = await agent.run("Fix the undefined control sequence error")

    # Create a plan for a complex task
    from agent.subagents.planner import create_plan_for_task
    plan = await create_plan_for_task(
        "Add a new methodology section",
        project_path="/path/to/project",
    )
"""

# Base classes
from agent.subagents.base import (
    Subagent,
    SubagentConfig,
    SubagentResult,
    get_subagent,
    list_subagents,
    register_subagent,
    run_subagent,
)

# Import subagent implementations to register them
from agent.subagents import research
from agent.subagents import compiler
from agent.subagents import planner
from agent.subagents import writing

# Re-export specific subagents for direct access
from agent.subagents.research import ResearchAgent
from agent.subagents.compiler import CompilerAgent
from agent.subagents.planner import PlannerAgent, create_plan_for_task
from agent.subagents.writing import WritingAgent


__all__ = [
    # Base classes
    "Subagent",
    "SubagentConfig",
    "SubagentResult",
    # Registry functions
    "get_subagent",
    "list_subagents",
    "register_subagent",
    "run_subagent",
    # Specific subagents
    "ResearchAgent",
    "CompilerAgent",
    "PlannerAgent",
    "WritingAgent",
    # Planning helpers
    "create_plan_for_task",
]
