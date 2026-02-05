"""
Research Tools

Tools for PDF reading and subagent delegation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic_ai import RunContext

from agent.deps import AuraDeps
from agent.errors import ToolError, ErrorCode
from agent.logging import get_logger, log_tool_call, log_tool_success, log_tool_error

logger = get_logger("tools.research")


async def read_pdf(
    ctx: "RunContext[AuraDeps]",
    filepath: str,
    max_pages: int = 20,
) -> str:
    """
    Read and extract text from a PDF file in the project.

    Use this to read academic papers, documentation, or any PDF files
    in the project directory.

    Args:
        filepath: Path to the PDF file relative to project root (e.g., "paper.pdf", "references/article.pdf")
        max_pages: Maximum number of pages to extract (default: 20)

    Returns:
        Extracted text from the PDF with page structure
    """
    from agent.tools.pdf_reader import read_local_pdf

    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    if not full_path.exists():
        return f"Error: PDF file not found: {filepath}"

    if not filepath.lower().endswith('.pdf'):
        return f"Error: Not a PDF file: {filepath}"

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        return f"Error: Path escapes project directory: {filepath}"

    try:
        doc = await read_local_pdf(
            path=str(full_path),
            max_pages=max_pages,
            max_chars=100000,
        )

        # Format output
        text = doc.get_text(max_pages=max_pages, max_chars=100000)
        return f"""PDF: {filepath}
Title: {doc.title}
Pages: {doc.num_pages}

--- Content ---

{text}
"""

    except ImportError:
        return "Error: PDF reading requires PyMuPDF. Install with: pip install PyMuPDF"
    except Exception as e:
        return f"Error reading PDF: {str(e)}"


async def delegate_to_subagent(
    ctx: "RunContext[AuraDeps]",
    subagent: str,
    task: str,
) -> str:
    """
    Delegate a task to a specialized subagent.

    Subagents are focused agents with specific expertise:
    - "research": Search Google Scholar for academic papers (returns papers with clickable links)
    - "compiler": Fix LaTeX compilation errors with deep knowledge of common issues

    Use delegation when:
    - You need to find academic papers (delegate to "research")
    - You have a complex compilation error that needs iterative fixing (delegate to "compiler")

    The subagent will work autonomously and return a result.

    Args:
        subagent: Name of the subagent ("research" or "compiler")
        task: Detailed description of what you want the subagent to do (DO NOT mention specific databases like arXiv)

    Returns:
        Result from the subagent's work
    """
    log_tool_call(logger, "delegate_to_subagent", subagent=subagent)
    from agent.subagents import get_subagent, list_subagents
    from agent.venue_hitl import get_research_preference_manager

    # Validate subagent name
    available = list_subagents()
    available_names = [s["name"] for s in available]

    if subagent not in available_names:
        log_tool_error(logger, "delegate_to_subagent", "INVALID_INPUT", f"Unknown subagent: {subagent}")
        raise ToolError(
            ErrorCode.INVALID_INPUT,
            f"Unknown subagent: '{subagent}'. Available: {', '.join(available_names)}",
            details={"available": available_names}
        )

    try:
        # Create context for subagent
        context = {
            "project_path": ctx.deps.project_path,
            "project_name": ctx.deps.project_name,
        }

        # For research subagent, request preferences via two-step HITL
        if subagent == "research":
            pref_manager = get_research_preference_manager()

            # Check if manager has event callbacks (meaning HITL is set up)
            if pref_manager._domain_event_callback and pref_manager._venue_event_callback:
                # Request research preferences through two-step HITL
                prefs = await pref_manager.request_research_preferences(
                    topic=task,
                    session_id=ctx.deps.session_id,
                )
                # Pass preferences to research agent
                context["domain"] = prefs.domain
                context["venue_filter"] = prefs.venues
                context["venue_preferences_asked"] = True
            else:
                # No HITL callbacks, proceed without filters
                context["domain"] = ""
                context["venue_filter"] = []
                context["venue_preferences_asked"] = False

        # Get and run subagent
        agent = get_subagent(subagent, project_path=ctx.deps.project_path)
        result = await agent.run(task, context)

        if result.success:
            log_tool_success(logger, "delegate_to_subagent", subagent=subagent)
            return f"[{subagent.upper()} AGENT RESULT]\n\n{result.output}"
        else:
            log_tool_error(logger, "delegate_to_subagent", "API_ERROR", result.error or "Subagent failed")
            return f"[{subagent.upper()} AGENT ERROR]\n\n{result.error}: {result.output}"

    except ToolError:
        raise
    except Exception as e:
        log_tool_error(logger, "delegate_to_subagent", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Subagent error: {str(e)}")


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_research_tools(agent):
    """
    Register all research tools with an agent.

    Args:
        agent: PydanticAI Agent instance
    """
    agent.tool(read_pdf)
    agent.tool(delegate_to_subagent)
