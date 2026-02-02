"""
File operation tools for the agent.

Provides read, edit, write, and glob operations on project files.
"""

from pathlib import Path
from typing import Optional
import fnmatch

from backend.tools.manager import hookimpl, ToolDefinition


def _validate_path(project_path: str, filepath: str) -> Path:
    """Validate and resolve a file path within a project."""
    project = Path(project_path).resolve()
    full_path = (project / filepath).resolve()

    # Security: ensure path is within project
    if not str(full_path).startswith(str(project)):
        raise ValueError(f"Path '{filepath}' is outside project directory")

    return full_path


async def read_file(project_path: str, filepath: str) -> str:
    """
    Read the contents of a file in the project.

    Args:
        project_path: Path to the project directory
        filepath: Relative path to the file within the project

    Returns:
        File contents as string, or error message
    """
    try:
        full_path = _validate_path(project_path, filepath)

        if not full_path.exists():
            return f"Error: File '{filepath}' not found"

        if not full_path.is_file():
            return f"Error: '{filepath}' is not a file"

        content = full_path.read_text(encoding="utf-8")

        # Add line numbers for context
        lines = content.split("\n")
        numbered = [f"{i+1:4d}│ {line}" for i, line in enumerate(lines)]

        return f"File: {filepath} ({len(lines)} lines)\n" + "\n".join(numbered)

    except Exception as e:
        return f"Error reading '{filepath}': {str(e)}"


async def edit_file(
    project_path: str,
    filepath: str,
    old_text: str,
    new_text: str,
) -> str:
    """
    Edit a file by replacing old_text with new_text.

    Args:
        project_path: Path to the project directory
        filepath: Relative path to the file within the project
        old_text: Text to find and replace
        new_text: Replacement text

    Returns:
        Success or error message
    """
    try:
        full_path = _validate_path(project_path, filepath)

        if not full_path.exists():
            return f"Error: File '{filepath}' not found"

        content = full_path.read_text(encoding="utf-8")

        if old_text not in content:
            return f"Error: Could not find the specified text in '{filepath}'"

        # Count occurrences
        count = content.count(old_text)
        if count > 1:
            # Replace only first occurrence to be safe
            new_content = content.replace(old_text, new_text, 1)
            full_path.write_text(new_content, encoding="utf-8")
            return f"✓ Replaced first occurrence in '{filepath}' (found {count} matches)"
        else:
            new_content = content.replace(old_text, new_text)
            full_path.write_text(new_content, encoding="utf-8")
            return f"✓ Updated '{filepath}'"

    except Exception as e:
        return f"Error editing '{filepath}': {str(e)}"


async def write_file(
    project_path: str,
    filepath: str,
    content: str,
) -> str:
    """
    Write content to a file (creates if doesn't exist).

    Args:
        project_path: Path to the project directory
        filepath: Relative path to the file within the project
        content: Content to write

    Returns:
        Success or error message
    """
    try:
        full_path = _validate_path(project_path, filepath)

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        existed = full_path.exists()
        full_path.write_text(content, encoding="utf-8")

        if existed:
            return f"✓ Overwrote '{filepath}'"
        else:
            return f"✓ Created '{filepath}'"

    except Exception as e:
        return f"Error writing '{filepath}': {str(e)}"


async def find_files(
    project_path: str,
    pattern: str = "*",
) -> str:
    """
    Find files matching a glob pattern.

    Args:
        project_path: Path to the project directory
        pattern: Glob pattern (e.g., "*.tex", "**/*.bib")

    Returns:
        List of matching file paths
    """
    try:
        project = Path(project_path).resolve()

        if not project.exists():
            return f"Error: Project path does not exist"

        matches = []
        for path in project.rglob(pattern):
            if path.is_file():
                # Skip hidden files and .aura directory
                rel_path = path.relative_to(project)
                if not any(part.startswith(".") for part in rel_path.parts):
                    matches.append(str(rel_path))

        if not matches:
            return f"No files matching '{pattern}' found"

        matches.sort()
        return f"Found {len(matches)} files:\n" + "\n".join(f"  {m}" for m in matches[:50])

    except Exception as e:
        return f"Error finding files: {str(e)}"


async def list_directory(
    project_path: str,
    dirpath: str = ".",
) -> str:
    """
    List contents of a directory.

    Args:
        project_path: Path to the project directory
        dirpath: Relative path to list (default: project root)

    Returns:
        Directory listing
    """
    try:
        full_path = _validate_path(project_path, dirpath)

        if not full_path.exists():
            return f"Error: Directory '{dirpath}' not found"

        if not full_path.is_dir():
            return f"Error: '{dirpath}' is not a directory"

        items = []
        for item in sorted(full_path.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                items.append(f"📄 {item.name} ({size} bytes)")

        if not items:
            return f"Directory '{dirpath}' is empty"

        return f"Contents of '{dirpath}':\n" + "\n".join(items)

    except Exception as e:
        return f"Error listing directory: {str(e)}"


# Register tools with pluggy
@hookimpl
def register_tools() -> list[ToolDefinition]:
    """Register file operation tools."""
    return [
        ToolDefinition(
            name="read_file",
            description="Read the contents of a file in the LaTeX project. Returns the file content with line numbers.",
            function=read_file,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "filepath": {
                        "type": "string",
                        "description": "Relative path to the file (e.g., 'main.tex', 'sections/intro.tex')",
                    },
                },
                "required": ["project_path", "filepath"],
            },
        ),
        ToolDefinition(
            name="edit_file",
            description="Edit a file by replacing specific text. Use this to make targeted changes to LaTeX files.",
            function=edit_file,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "filepath": {
                        "type": "string",
                        "description": "Relative path to the file",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find and replace",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "New text to insert",
                    },
                },
                "required": ["project_path", "filepath", "old_text", "new_text"],
            },
        ),
        ToolDefinition(
            name="write_file",
            description="Write content to a file, creating it if it doesn't exist. Use for creating new files or completely replacing content.",
            function=write_file,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "filepath": {
                        "type": "string",
                        "description": "Relative path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["project_path", "filepath", "content"],
            },
        ),
        ToolDefinition(
            name="find_files",
            description="Find files matching a glob pattern in the project. Use to discover project structure.",
            function=find_files,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '*.tex', '**/*.bib', 'figures/*.png')",
                    },
                },
                "required": ["project_path", "pattern"],
            },
        ),
        ToolDefinition(
            name="list_directory",
            description="List the contents of a directory in the project.",
            function=list_directory,
            parameters={
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Path to the project directory",
                    },
                    "dirpath": {
                        "type": "string",
                        "description": "Relative path to the directory (default: project root)",
                    },
                },
                "required": ["project_path"],
            },
        ),
    ]
