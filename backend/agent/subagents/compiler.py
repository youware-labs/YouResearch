"""
Compiler Subagent

Specialized agent for fixing LaTeX compilation errors.
This agent has deep knowledge of:
- Common LaTeX errors and their causes
- Package conflicts and resolutions
- BibTeX/bibliography issues
- Mathematical typesetting problems

Workflow:
1. Analyze the error log
2. Identify the root cause
3. Read the problematic file(s)
4. Propose and apply fixes
5. Recompile to verify
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext

from agent.subagents.base import (
    Subagent,
    SubagentConfig,
    register_subagent,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Dependencies
# =============================================================================

@dataclass
class CompilerDeps:
    """Dependencies for the compiler agent."""
    project_path: str
    main_file: str = "main.tex"


# =============================================================================
# Compiler Agent
# =============================================================================

COMPILER_SYSTEM_PROMPT = """You are a specialized LaTeX compilation expert.

Your job is to fix LaTeX compilation errors. You have access to:
- read_file: Read any file in the project
- edit_file: Make targeted edits to fix errors
- compile_and_check: Compile and see if errors are fixed

WORKFLOW:
1. First, carefully analyze the error message to understand the problem
2. Identify which file and line the error occurs on
3. Read the relevant file(s) to understand the context
4. Make a targeted fix - change only what's necessary
5. Compile to verify the fix worked
6. If the fix didn't work, analyze the new error and iterate

COMMON LATEX ERRORS AND FIXES:

1. **Missing package**: "Undefined control sequence \\xyz"
   → Add \\usepackage{packagename} to preamble

2. **Unmatched braces**: "Missing } inserted"
   → Find and fix the unmatched { or }

3. **Math mode errors**: "Missing $ inserted"
   → Ensure math content is within $ $ or \\[ \\]

4. **Environment mismatch**: "\\begin{X} ended by \\end{Y}"
   → Match the environment names

5. **Bibliography errors**: "Citation undefined"
   → Check .bib file exists and citation key is correct

6. **File not found**: "File 'X.tex' not found"
   → Check file path and spelling

7. **Missing \\item**: "Something's wrong--perhaps a missing \\item"
   → Add \\item in itemize/enumerate environments

RULES:
- Always read the file before editing
- Make minimal, targeted changes
- If unsure, explain options and let main agent decide
- Never delete large sections of content without asking
"""


@register_subagent("compiler")
class CompilerAgent(Subagent[CompilerDeps]):
    """
    Compiler subagent for fixing LaTeX errors.

    Tools:
        - read_file: Read project files
        - edit_file: Edit files to fix errors
        - compile_and_check: Compile and check for errors
    """

    def __init__(self, project_path: str = "", **kwargs):
        config = SubagentConfig(
            name="compiler",
            description="Fix LaTeX compilation errors with targeted edits",
            max_iterations=15,  # May need multiple attempts
            timeout=120.0,
            use_haiku=False,  # Use smarter model for complex debugging
        )
        super().__init__(config)
        self._default_project_path = project_path

    @property
    def system_prompt(self) -> str:
        return COMPILER_SYSTEM_PROMPT

    def _create_deps(self, context: dict[str, Any]) -> CompilerDeps:
        """Create dependencies for compiler agent."""
        return CompilerDeps(
            project_path=context.get("project_path", self._default_project_path),
            main_file=context.get("main_file", "main.tex"),
        )

    def _create_agent(self) -> Agent[CompilerDeps, str]:
        """Create the compiler agent with tools."""
        agent = Agent(
            model=self._get_model(),
            system_prompt=self.system_prompt,
            deps_type=CompilerDeps,
            retries=2,
        )

        # Register tools
        @agent.tool
        async def read_file(
            ctx: RunContext[CompilerDeps],
            filepath: str,
        ) -> str:
            """
            Read a file from the LaTeX project.

            Args:
                filepath: Path relative to project root (e.g., "main.tex", "sections/intro.tex")

            Returns:
                File contents with line numbers
            """
            project_path = ctx.deps.project_path
            full_path = Path(project_path) / filepath

            if not full_path.exists():
                return f"Error: File not found: {filepath}"

            if not full_path.is_file():
                return f"Error: Not a file: {filepath}"

            # Security: ensure path is within project
            try:
                full_path.resolve().relative_to(Path(project_path).resolve())
            except ValueError:
                return f"Error: Path escapes project directory: {filepath}"

            try:
                content = full_path.read_text()
                lines = content.split('\n')
                numbered = [f"{i+1:4}│ {line}" for i, line in enumerate(lines)]
                return f"File: {filepath} ({len(lines)} lines)\n" + "\n".join(numbered)
            except Exception as e:
                return f"Error reading file: {e}"

        @agent.tool
        async def edit_file(
            ctx: RunContext[CompilerDeps],
            filepath: str,
            old_string: str,
            new_string: str,
        ) -> str:
            """
            Edit a file by replacing text.

            Use this to make targeted fixes. The old_string must match exactly.

            Args:
                filepath: Path relative to project root
                old_string: Exact text to find and replace
                new_string: Text to replace with

            Returns:
                Success message or error
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

                if old_string not in content:
                    return f"Error: Could not find the specified text in {filepath}"

                count = content.count(old_string)
                if count > 1:
                    return f"Error: Found {count} occurrences. Please provide more context for unique match."

                new_content = content.replace(old_string, new_string, 1)
                full_path.write_text(new_content)

                return f"Successfully edited {filepath}"
            except Exception as e:
                return f"Error editing file: {e}"

        @agent.tool
        async def add_package(
            ctx: RunContext[CompilerDeps],
            package_name: str,
            options: str = "",
        ) -> str:
            """
            Add a \\usepackage command to the preamble.

            This finds the preamble (between \\documentclass and \\begin{document})
            and adds the package there.

            Args:
                package_name: Name of the package (e.g., "amsmath", "graphicx")
                options: Optional package options (e.g., "utf8" for inputenc)

            Returns:
                Success message or error
            """
            project_path = ctx.deps.project_path
            main_file = ctx.deps.main_file
            full_path = Path(project_path) / main_file

            if not full_path.exists():
                return f"Error: Main file not found: {main_file}"

            try:
                content = full_path.read_text()

                # Check if package already loaded
                if f"\\usepackage{{{package_name}}}" in content:
                    return f"Package '{package_name}' is already loaded"

                if f"\\usepackage[" in content and f"]{{{package_name}}}" in content:
                    return f"Package '{package_name}' is already loaded"

                # Find position to insert (after last \usepackage or after \documentclass)
                lines = content.split('\n')
                insert_idx = -1

                for i, line in enumerate(lines):
                    if line.strip().startswith('\\usepackage'):
                        insert_idx = i
                    elif '\\begin{document}' in line:
                        if insert_idx == -1:
                            insert_idx = i - 1
                        break

                if insert_idx == -1:
                    return "Error: Could not find preamble location"

                # Create usepackage line
                if options:
                    new_line = f"\\usepackage[{options}]{{{package_name}}}"
                else:
                    new_line = f"\\usepackage{{{package_name}}}"

                # Insert
                lines.insert(insert_idx + 1, new_line)
                full_path.write_text('\n'.join(lines))

                return f"Added \\usepackage{{{package_name}}} to preamble"

            except Exception as e:
                return f"Error adding package: {e}"

        @agent.tool
        async def compile_and_check(
            ctx: RunContext[CompilerDeps],
            main_file: str = "",
        ) -> str:
            """
            Compile the LaTeX project and return the result.

            Args:
                main_file: Main .tex file to compile (default: use project default)

            Returns:
                "Compilation successful!" or error log excerpt
            """
            from services.docker import get_docker_latex

            project_path = ctx.deps.project_path
            if not main_file:
                main_file = ctx.deps.main_file

            try:
                docker = get_docker_latex()
                result = await docker.compile(project_path, main_file)

                if result.success:
                    return f"Compilation successful! Output: {result.pdf_path}"
                else:
                    # Return relevant portion of log
                    log = result.log_output or result.error_summary or "Unknown error"
                    return f"Compilation failed:\n{log[-3000:]}"

            except Exception as e:
                return f"Compilation error: {e}"

        @agent.tool
        async def list_files(
            ctx: RunContext[CompilerDeps],
            pattern: str = "*.tex",
        ) -> str:
            """
            List files matching a pattern.

            Args:
                pattern: Glob pattern (default: *.tex)

            Returns:
                List of matching files
            """
            project_path = Path(ctx.deps.project_path)

            try:
                matches = list(project_path.glob(pattern))
                if not matches:
                    return f"No files found matching: {pattern}"

                relative = sorted([str(m.relative_to(project_path)) for m in matches if m.is_file()])
                return f"Found {len(relative)} files:\n" + "\n".join(f"  {f}" for f in relative[:30])
            except Exception as e:
                return f"Error listing files: {e}"

        @agent.tool
        async def think(ctx: RunContext[CompilerDeps], thought: str) -> str:
            """
            Think through the error and solution step-by-step.

            Use this to reason about:
            - What the error message means
            - Possible causes
            - Which fix to try

            Args:
                thought: Your reasoning process

            Returns:
                Acknowledgment to continue
            """
            return "Thinking recorded. Continue with your fix."

        return agent
