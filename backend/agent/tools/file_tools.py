"""
File Tools

Tools for file operations: read, write, edit, list, find, search.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai import RunContext

from agent.deps import AuraDeps
from agent.errors import ToolError, ErrorCode
from agent.logging import get_logger, log_tool_call, log_tool_success, log_tool_error

logger = get_logger("tools.file")


async def read_file(ctx: "RunContext[AuraDeps]", filepath: str) -> str:
    """
    Read a file from the LaTeX project.

    Args:
        filepath: Path relative to project root (e.g., "main.tex", "sections/intro.tex")

    Returns:
        File contents with line numbers
    """
    log_tool_call(logger, "read_file", filepath=filepath)
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        log_tool_error(logger, "read_file", "PATH_ESCAPE", f"Path escapes project: {filepath}")
        raise ToolError(ErrorCode.PATH_ESCAPE, f"Path escapes project directory: {filepath}")

    if not full_path.exists():
        log_tool_error(logger, "read_file", "FILE_NOT_FOUND", f"File not found: {filepath}")
        raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")

    if not full_path.is_file():
        log_tool_error(logger, "read_file", "INVALID_PATH", f"Not a file: {filepath}")
        raise ToolError(ErrorCode.INVALID_PATH, f"Not a file: {filepath}")

    try:
        content = full_path.read_text()
        lines = content.split('\n')
        numbered = [f"{i+1:4}│ {line}" for i, line in enumerate(lines)]
        log_tool_success(logger, "read_file", lines=len(lines))
        return f"File: {filepath} ({len(lines)} lines)\n" + "\n".join(numbered)
    except PermissionError:
        log_tool_error(logger, "read_file", "PERMISSION_DENIED", f"Cannot read: {filepath}")
        raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot read file: {filepath}")
    except Exception as e:
        log_tool_error(logger, "read_file", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Error reading file: {e}")


async def read_file_lines(
    ctx: "RunContext[AuraDeps]",
    filepath: str,
    start_line: int,
    end_line: int,
) -> str:
    """
    Read specific lines from a file.

    Use this when you know which lines you need, to avoid reading the entire file.

    Args:
        filepath: Path relative to project root
        start_line: First line to read (1-indexed)
        end_line: Last line to read (inclusive)

    Returns:
        Requested lines with line numbers
    """
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    if not full_path.exists():
        return f"Error: File not found: {filepath}"

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        return f"Error: Path escapes project directory: {filepath}"

    try:
        content = full_path.read_text()
        lines = content.split('\n')

        # Validate line numbers
        if start_line < 1:
            start_line = 1
        if end_line > len(lines):
            end_line = len(lines)
        if start_line > end_line:
            return f"Error: start_line ({start_line}) > end_line ({end_line})"

        # Extract lines (convert to 0-indexed)
        selected = lines[start_line - 1:end_line]
        numbered = [f"{i:4}│ {line}" for i, line in enumerate(selected, start=start_line)]

        return f"File: {filepath} (lines {start_line}-{end_line} of {len(lines)}):\n" + "\n".join(numbered)

    except Exception as e:
        return f"Error reading file: {e}"


async def edit_file(
    ctx: "RunContext[AuraDeps]",
    filepath: str,
    old_string: str,
    new_string: str,
    check_hitl_func=None,
) -> str:
    """
    Edit a file by replacing text.

    Args:
        filepath: Path relative to project root
        old_string: Exact text to find and replace
        new_string: Text to replace with
        check_hitl_func: HITL check function (injected)

    Returns:
        Success message or error
    """
    log_tool_call(logger, "edit_file", filepath=filepath)

    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        log_tool_error(logger, "edit_file", "PATH_ESCAPE", f"Path escapes project: {filepath}")
        raise ToolError(ErrorCode.PATH_ESCAPE, f"Path escapes project directory: {filepath}")

    if not full_path.exists():
        log_tool_error(logger, "edit_file", "FILE_NOT_FOUND", f"File not found: {filepath}")
        raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")

    # Read current content for validation and diff preview
    try:
        current_content = full_path.read_text()
    except PermissionError:
        log_tool_error(logger, "edit_file", "PERMISSION_DENIED", f"Cannot read: {filepath}")
        raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot read file: {filepath}")

    # Validate old_string exists and is unique
    if old_string not in current_content:
        log_tool_error(logger, "edit_file", "INVALID_INPUT", "Text not found in file")
        raise ToolError(ErrorCode.INVALID_INPUT, f"Could not find the specified text in {filepath}")

    count = current_content.count(old_string)
    if count > 1:
        log_tool_error(logger, "edit_file", "INVALID_INPUT", f"Found {count} occurrences")
        raise ToolError(
            ErrorCode.INVALID_INPUT,
            f"Found {count} occurrences. Please provide more context for unique match.",
            details={"count": count}
        )

    # Compute new content for diff preview
    new_content = current_content.replace(old_string, new_string, 1)

    # HITL check - pass diff preview data for async mode
    if check_hitl_func:
        should_proceed, message, modified_args = await check_hitl_func(
            ctx, "edit_file",
            {"filepath": filepath, "old_string": old_string, "new_string": new_string},
            file_path=filepath,
            old_content=current_content,
            new_content=new_content,
        )
        if not should_proceed:
            return message

        # Use modified args if user edited them
        if modified_args:
            filepath = modified_args.get("filepath", filepath)
            old_string = modified_args.get("old_string", old_string)
            new_string = modified_args.get("new_string", new_string)
            # Re-read and re-compute if args changed
            full_path = Path(project_path) / filepath
            current_content = full_path.read_text()
            new_content = current_content.replace(old_string, new_string, 1)

    try:
        full_path.write_text(new_content)
        log_tool_success(logger, "edit_file", filepath=filepath)
        return f"Successfully edited {filepath}"
    except PermissionError:
        log_tool_error(logger, "edit_file", "PERMISSION_DENIED", f"Cannot write: {filepath}")
        raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot write to file: {filepath}")
    except Exception as e:
        log_tool_error(logger, "edit_file", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Error editing file: {e}")


async def write_file(
    ctx: "RunContext[AuraDeps]",
    filepath: str,
    content: str,
    check_hitl_func=None,
) -> str:
    """
    Write content to a file (creates or overwrites).

    Args:
        filepath: Path relative to project root
        content: Content to write
        check_hitl_func: HITL check function (injected)

    Returns:
        Success message or error
    """
    log_tool_call(logger, "write_file", filepath=filepath, size=len(content))

    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        log_tool_error(logger, "write_file", "PATH_ESCAPE", f"Path escapes project: {filepath}")
        raise ToolError(ErrorCode.PATH_ESCAPE, f"Path escapes project directory: {filepath}")

    # Get current content for diff preview (empty if file doesn't exist)
    old_content = ""
    if full_path.exists():
        try:
            old_content = full_path.read_text()
        except PermissionError:
            log_tool_error(logger, "write_file", "PERMISSION_DENIED", f"Cannot read: {filepath}")
            raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot read file: {filepath}")

    # HITL check - pass diff preview data for async mode
    if check_hitl_func:
        should_proceed, message, modified_args = await check_hitl_func(
            ctx, "write_file",
            {"filepath": filepath, "content": content},
            file_path=filepath,
            old_content=old_content,
            new_content=content,
        )
        if not should_proceed:
            return message

        # Use modified args if user edited them
        if modified_args:
            filepath = modified_args.get("filepath", filepath)
            if "content" in modified_args:
                content = modified_args["content"]
            full_path = Path(project_path) / filepath

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        log_tool_success(logger, "write_file", filepath=filepath, size=len(content))
        return f"Successfully wrote {filepath} ({len(content)} chars)"
    except PermissionError:
        log_tool_error(logger, "write_file", "PERMISSION_DENIED", f"Cannot write: {filepath}")
        raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot write to file: {filepath}")
    except Exception as e:
        log_tool_error(logger, "write_file", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Error writing file: {e}")


async def list_files(ctx: "RunContext[AuraDeps]", directory: str = ".") -> str:
    """
    List files in a directory.

    Args:
        directory: Directory relative to project root (default: root)

    Returns:
        List of files and directories
    """
    log_tool_call(logger, "list_files", directory=directory)
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / directory

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        log_tool_error(logger, "list_files", "PATH_ESCAPE", f"Path escapes project: {directory}")
        raise ToolError(ErrorCode.PATH_ESCAPE, f"Path escapes project directory: {directory}")

    if not full_path.exists():
        log_tool_error(logger, "list_files", "FILE_NOT_FOUND", f"Directory not found: {directory}")
        raise ToolError(ErrorCode.FILE_NOT_FOUND, f"Directory not found: {directory}")

    if not full_path.is_dir():
        log_tool_error(logger, "list_files", "INVALID_PATH", f"Not a directory: {directory}")
        raise ToolError(ErrorCode.INVALID_PATH, f"Not a directory: {directory}")

    try:
        items = []
        for item in sorted(full_path.iterdir()):
            if item.name.startswith('.'):
                continue  # Skip hidden files
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                items.append(f"📄 {item.name} ({size} bytes)")

        log_tool_success(logger, "list_files", count=len(items))
        return f"Contents of {directory}:\n" + "\n".join(items) if items else f"Directory {directory} is empty"
    except PermissionError:
        log_tool_error(logger, "list_files", "PERMISSION_DENIED", f"Cannot access: {directory}")
        raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot access directory: {directory}")
    except Exception as e:
        log_tool_error(logger, "list_files", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Error listing directory: {e}")


async def find_files(ctx: "RunContext[AuraDeps]", pattern: str) -> str:
    """
    Find files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*.tex", "**/*.bib")

    Returns:
        List of matching files
    """
    log_tool_call(logger, "find_files", pattern=pattern)
    project_path = Path(ctx.deps.project_path)

    try:
        matches = list(project_path.glob(pattern))
        if not matches:
            log_tool_success(logger, "find_files", count=0)
            return f"No files found matching: {pattern}"

        # Make paths relative and sort
        relative = sorted([str(m.relative_to(project_path)) for m in matches if m.is_file()])
        log_tool_success(logger, "find_files", count=len(relative))
        return f"Found {len(relative)} files matching '{pattern}':\n" + "\n".join(f"  {f}" for f in relative[:50])
    except Exception as e:
        log_tool_error(logger, "find_files", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Error searching files: {e}")


async def search_in_file(
    ctx: "RunContext[AuraDeps]",
    filepath: str,
    pattern: str,
    context_lines: int = 2,
) -> str:
    """
    Search for a pattern within a file and return matching lines with context.

    This is like grep - use it to find specific content without reading the entire file.
    ALWAYS use this tool first when looking for specific content in a file.

    Args:
        filepath: Path relative to project root (e.g., "main.tex")
        pattern: Text or regex pattern to search for (case-insensitive)
        context_lines: Number of lines to show before/after each match (default: 2)

    Returns:
        Matching lines with line numbers and context
    """
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    if not full_path.exists():
        return f"Error: File not found: {filepath}"

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        return f"Error: Path escapes project directory: {filepath}"

    try:
        content = full_path.read_text()
        lines = content.split('\n')

        # Compile pattern (case-insensitive)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # If invalid regex, treat as literal string
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        # Find matching lines
        matches = []
        for i, line in enumerate(lines):
            if regex.search(line):
                matches.append(i)

        if not matches:
            return f"No matches found for '{pattern}' in {filepath}"

        # Build output with context
        output = [f"Found {len(matches)} matches for '{pattern}' in {filepath}:\n"]

        shown_lines = set()
        for match_idx in matches:
            start = max(0, match_idx - context_lines)
            end = min(len(lines), match_idx + context_lines + 1)

            # Add separator if there's a gap
            if shown_lines and start > max(shown_lines) + 1:
                output.append("  ---")

            for i in range(start, end):
                if i not in shown_lines:
                    marker = ">>>" if i == match_idx else "   "
                    output.append(f"{marker} {i+1:4}│ {lines[i]}")
                    shown_lines.add(i)

        return "\n".join(output)

    except Exception as e:
        return f"Error searching file: {e}"


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_file_tools(agent, check_hitl_func=None):
    """
    Register all file tools with an agent.

    Args:
        agent: PydanticAI Agent instance
        check_hitl_func: HITL check function for edit/write operations
    """
    # Register read-only tools directly
    agent.tool(read_file)
    agent.tool(read_file_lines)
    agent.tool(list_files)
    agent.tool(find_files)
    agent.tool(search_in_file)

    # For edit/write tools, we need to wrap them to inject the HITL function
    @agent.tool
    async def edit_file_tool(
        ctx: "RunContext[AuraDeps]",
        filepath: str,
        old_string: str,
        new_string: str,
    ) -> str:
        """
        Edit a file by replacing text.

        Args:
            filepath: Path relative to project root
            old_string: Exact text to find and replace
            new_string: Text to replace with

        Returns:
            Success message or error
        """
        return await edit_file(ctx, filepath, old_string, new_string, check_hitl_func)

    @agent.tool
    async def write_file_tool(
        ctx: "RunContext[AuraDeps]",
        filepath: str,
        content: str,
    ) -> str:
        """
        Write content to a file (creates or overwrites).

        Args:
            filepath: Path relative to project root
            content: Content to write

        Returns:
            Success message or error
        """
        return await write_file(ctx, filepath, content, check_hitl_func)
