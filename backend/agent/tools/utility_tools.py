"""
Utility Tools

General utility tools: think (reasoning), etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import RunContext

from agent.deps import AuraDeps


async def think(ctx: RunContext[AuraDeps], thought: str) -> str:
    """
    Think through a complex problem step-by-step.

    Use this for internal reasoning AFTER gathering information. Good for:
    - Planning multi-file edits
    - Debugging compilation errors
    - Considering mathematical proofs
    - Weighing different approaches

    IMPORTANT: Only use this tool to reason about information you have ALREADY
    retrieved via read_file or other tools. NEVER use this to imagine or guess
    what files might contain - always read files first.

    The thought content helps you reason but is not shown to the user.

    Args:
        thought: Your step-by-step reasoning process

    Returns:
        Acknowledgment to continue
    """
    # The thought is captured in the tool call for context
    # This helps Claude's reasoning chain
    return "Thinking recorded. Continue with your analysis or take action."


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_utility_tools(agent):
    """
    Register all utility tools with an agent.

    Args:
        agent: PydanticAI Agent instance
    """
    agent.tool(think)
