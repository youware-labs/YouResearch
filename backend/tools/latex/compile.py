"""
LaTeX compilation tools for the agent.

Provides tools for compiling LaTeX and handling errors.
"""

from backend.tools.manager import hookimpl, ToolDefinition
from backend.services.docker import DockerLatex, CompileResult

# Shared Docker LaTeX instance
_docker_latex: DockerLatex | None = None


def _get_docker_latex() -> DockerLatex:
    """Get or create the Docker LaTeX instance."""
    global _docker_latex
    if _docker_latex is None:
        _docker_latex = DockerLatex()
    return _docker_latex


async def compile_latex(
    project_path: str,
    filename: str = "main.tex",
) -> str:
    """
    Compile a LaTeX file to PDF.

    Args:
        project_path: Path to the project directory
        filename: Name of the .tex file to compile (default: main.tex)

    Returns:
        Compilation result with success status and any errors
    """
    docker = _get_docker_latex()

    result: CompileResult = await docker.compile(
        project_path=project_path,
        filename=filename,
    )

    if result.success:
        return f"""✓ Compilation successful!
PDF generated at: {result.pdf_path}

The document compiled without errors."""
    else:
        error_msg = f"""✗ Compilation failed.

Errors:
{result.error_summary}

To fix these errors, read the problematic file and make corrections using edit_file."""
        return error_msg


async def check_latex_syntax(
    project_path: str,
    filename: str = "main.tex",
) -> str:
    """
    Quick syntax check without full compilation.

    Args:
        project_path: Path to the project directory
        filename: Name of the .tex file to check

    Returns:
        Syntax check result
    """
    docker = _get_docker_latex()

    result = await docker.check_syntax(
        project_path=project_path,
        filename=filename,
    )

    if result.success:
        return f"✓ Syntax check passed for '{filename}'"
    else:
        return f"""✗ Syntax errors found in '{filename}':

{result.error_summary}"""


async def get_compilation_log(
    project_path: str,
    filename: str = "main.tex",
) -> str:
    """
    Get the LaTeX compilation log for debugging.

    Args:
        project_path: Path to the project directory
        filename: Name of the .tex file (will read corresponding .log)

    Returns:
        Last 100 lines of the compilation log
    """
    from pathlib import Path

    log_name = filename.rsplit(".", 1)[0] + ".log"
    log_path = Path(project_path) / log_name

    if not log_path.exists():
        return f"No compilation log found. Run compile_latex first."

    content = log_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.split("\n")

    # Return last 100 lines
    if len(lines) > 100:
        return f"... (showing last 100 of {len(lines)} lines)\n\n" + "\n".join(lines[-100:])
    else:
        return content


# Register tools with pluggy
@hookimpl
def register_tools() -> list[ToolDefinition]:
    """Register LaTeX tools."""
    return [
        ToolDefinition(
            name="compile_latex",
            description="Compile a LaTeX document to PDF. Returns success status and any compilation errors. Always compile after making changes to verify the document builds correctly.",
            function=compile_latex,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Name of the .tex file to compile (default: main.tex)",
                    },
                },
                "required": ["project_path"],
            },
        ),
        ToolDefinition(
            name="check_latex_syntax",
            description="Quick syntax check for a LaTeX file without full compilation. Faster than compile_latex for catching obvious errors.",
            function=check_latex_syntax,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Name of the .tex file to check (default: main.tex)",
                    },
                },
                "required": ["project_path"],
            },
        ),
        ToolDefinition(
            name="get_compilation_log",
            description="Get the detailed LaTeX compilation log for debugging complex errors.",
            function=get_compilation_log,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Name of the .tex file (default: main.tex)",
                    },
                },
                "required": ["project_path"],
            },
        ),
    ]
