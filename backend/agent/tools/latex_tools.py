"""
LaTeX Tools

Tools for LaTeX compilation, syntax checking, and content generation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai import RunContext

from agent.deps import AuraDeps
from agent.errors import ToolError, ErrorCode
from agent.logging import get_logger, log_tool_call, log_tool_success, log_tool_error

logger = get_logger("tools.latex")


# =============================================================================
# Helper Functions
# =============================================================================

def escape_latex(text: str) -> str:
    """Escape LaTeX special characters in text."""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('^', r'\^{}'),
        ('~', r'\~{}'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def escape_latex_preserve_math(text: str) -> str:
    """Escape LaTeX special characters in text (preserves math mode)."""
    # Don't escape text inside math mode ($...$)
    parts = re.split(r'(\$[^$]+\$)', text)
    escaped_parts = []
    for part in parts:
        if part.startswith('$') and part.endswith('$'):
            escaped_parts.append(part)
        else:
            replacements = [
                ('\\', r'\textbackslash{}'),
                ('&', r'\&'),
                ('%', r'\%'),
                ('#', r'\#'),
                ('_', r'\_'),
                ('{', r'\{'),
                ('}', r'\}'),
                ('^', r'\^{}'),
                ('~', r'\~{}'),
            ]
            for old, new in replacements:
                part = part.replace(old, new)
            escaped_parts.append(part)
    return ''.join(escaped_parts)


# =============================================================================
# Compilation Tools
# =============================================================================

async def compile_latex(
    ctx: "RunContext[AuraDeps]",
    main_file: str = "main.tex",
) -> str:
    """
    Compile the LaTeX project.

    Uses local TeX installation (MacTeX/TeX Live) if available,
    otherwise falls back to Docker compilation.

    Args:
        main_file: Main .tex file to compile (default: main.tex)

    Returns:
        Compilation result with any errors
    """
    log_tool_call(logger, "compile_latex", main_file=main_file)
    from services.unified_latex import get_unified_latex

    latex = get_unified_latex()
    project_path = ctx.deps.project_path

    try:
        result = await latex.compile(project_path, main_file)

        if result.success:
            backend_info = f" (using {result.backend_used})" if result.backend_used else ""
            log_tool_success(logger, "compile_latex", backend=result.backend_used)
            return f"Compilation successful{backend_info}! Output: {result.pdf_path}"
        elif result.tex_not_available:
            log_tool_error(logger, "compile_latex", "NOT_IMPLEMENTED", "No LaTeX compiler")
            return f"No LaTeX compiler available:\n{result.error_summary}"
        else:
            log_tool_error(logger, "compile_latex", "COMPILATION_FAILED", result.error_summary or "Unknown error")
            # Return last 2000 chars of log
            log_excerpt = result.log[-2000:] if result.log else ""
            return f"Compilation failed:\n{result.error_summary or ''}\n{log_excerpt}"
    except Exception as e:
        log_tool_error(logger, "compile_latex", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Compilation error: {e}")


async def check_latex_syntax(
    ctx: "RunContext[AuraDeps]",
    filepath: str,
) -> str:
    """
    Check a LaTeX file for common syntax errors.

    This is a quick check without full compilation.

    Args:
        filepath: Path to the .tex file

    Returns:
        List of potential issues or "No issues found"
    """
    log_tool_call(logger, "check_latex_syntax", filepath=filepath)
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    if not full_path.exists():
        log_tool_error(logger, "check_latex_syntax", "FILE_NOT_FOUND", f"File not found: {filepath}")
        raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")

    try:
        content = full_path.read_text()
        issues = []

        # Check for unmatched braces
        brace_count = content.count('{') - content.count('}')
        if brace_count != 0:
            issues.append(f"Unmatched braces: {'+' if brace_count > 0 else ''}{brace_count}")

        # Check for unmatched environments
        begins = re.findall(r'\\begin\{(\w+)\}', content)
        ends = re.findall(r'\\end\{(\w+)\}', content)
        for env in set(begins):
            diff = begins.count(env) - ends.count(env)
            if diff != 0:
                issues.append(f"Unmatched \\begin{{{env}}}: {'+' if diff > 0 else ''}{diff}")

        # Check for common mistakes
        if '\\cite{}' in content:
            issues.append("Empty \\cite{} command found")
        if '\\ref{}' in content:
            issues.append("Empty \\ref{} command found")

        if issues:
            log_tool_success(logger, "check_latex_syntax", issues=len(issues))
            return f"Found {len(issues)} potential issues in {filepath}:\n" + "\n".join(f"  - {i}" for i in issues)
        else:
            log_tool_success(logger, "check_latex_syntax", issues=0)
            return f"No syntax issues found in {filepath}"
    except ToolError:
        raise
    except PermissionError:
        log_tool_error(logger, "check_latex_syntax", "PERMISSION_DENIED", f"Cannot read: {filepath}")
        raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot read file: {filepath}")
    except Exception as e:
        log_tool_error(logger, "check_latex_syntax", "INTERNAL_ERROR", str(e))
        raise ToolError(ErrorCode.INTERNAL_ERROR, f"Error checking syntax: {e}")


# =============================================================================
# Content Generation Tools
# =============================================================================

async def create_table(
    ctx: "RunContext[AuraDeps]",
    data: str,
    caption: str,
    label: str = "",
    style: str = "booktabs",
) -> str:
    """
    Generate a LaTeX table from data.

    Args:
        data: Table data in CSV or markdown format:
              CSV: "Header1,Header2\\nValue1,Value2"
              Markdown: "| H1 | H2 |\\n| v1 | v2 |"
        caption: Table caption
        label: Label for referencing (e.g., "results" -> \\label{tab:results})
        style: Table style - "booktabs" (professional) or "basic"

    Returns:
        Complete LaTeX table code ready to paste
    """
    # Parse data
    lines = data.strip().split("\n")
    rows = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("|--") or line.startswith("|-"):
            continue

        # Handle markdown format
        if "|" in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
        # Handle CSV format
        else:
            cells = [c.strip() for c in line.split(",")]

        if cells:
            rows.append(cells)

    if not rows:
        return "Error: Could not parse table data"

    # Determine column count and alignment
    num_cols = max(len(row) for row in rows)

    # Detect numeric columns for right-alignment
    alignments = []
    for col in range(num_cols):
        is_numeric = True
        for row in rows[1:]:  # Skip header
            if col < len(row):
                val = row[col].strip()
                if not re.match(r"^[\d.,]+%?$", val) and val:
                    is_numeric = False
                    break
        alignments.append("r" if is_numeric else "l")

    # First column usually left-aligned
    if alignments:
        alignments[0] = "l"

    alignment_str = "".join(alignments)

    # Build table
    if style == "booktabs":
        table_lines = [
            r"\begin{table}[htbp]",
            r"    \centering",
            f"    \\caption{{{caption}}}",
        ]
        if label:
            table_lines.append(f"    \\label{{tab:{label}}}")
        table_lines.extend([
            f"    \\begin{{tabular}}{{{alignment_str}}}",
            r"        \toprule",
        ])

        # Header row
        if rows:
            header = " & ".join(f"\\textbf{{{escape_latex(cell)}}}" for cell in rows[0])
            table_lines.append(f"        {header} \\\\")
            table_lines.append(r"        \midrule")

        # Data rows
        for row in rows[1:]:
            padded_row = row + [''] * (num_cols - len(row))
            row_str = " & ".join(escape_latex(cell) for cell in padded_row)
            table_lines.append(f"        {row_str} \\\\")

        table_lines.extend([
            r"        \bottomrule",
            r"    \end{tabular}",
            r"\end{table}",
        ])
    else:
        # Basic style
        table_lines = [
            r"\begin{table}[htbp]",
            r"    \centering",
            f"    \\caption{{{caption}}}",
        ]
        if label:
            table_lines.append(f"    \\label{{tab:{label}}}")
        table_lines.extend([
            f"    \\begin{{tabular}}{{|{alignment_str}|}}",
            r"        \hline",
        ])

        for i, row in enumerate(rows):
            padded_row = row + [''] * (num_cols - len(row))
            row_str = " & ".join(escape_latex(cell) for cell in padded_row)
            table_lines.append(f"        {row_str} \\\\")
            table_lines.append(r"        \hline")

        table_lines.extend([
            r"    \end{tabular}",
            r"\end{table}",
        ])

    return "\n".join(table_lines)


async def create_figure(
    ctx: "RunContext[AuraDeps]",
    description: str,
    figure_type: str = "tikz",
    caption: str = "",
    label: str = "",
    data: str = "",
) -> str:
    """
    Generate a LaTeX figure from description.

    Args:
        description: What the figure should show (e.g., "flowchart of training pipeline")
        figure_type: Type of figure:
                    - "tikz": General diagrams
                    - "pgfplots-bar": Bar chart
                    - "pgfplots-line": Line plot
                    - "pgfplots-scatter": Scatter plot
        caption: Figure caption
        label: Label for referencing (e.g., "architecture" -> \\label{fig:architecture})
        data: For plots, provide data as CSV: "x,y1,y2\\n1,2,3\\n2,4,5"

    Returns:
        Complete LaTeX figure code
    """
    if figure_type == "tikz":
        figure_code = r"""
\begin{figure}[htbp]
    \centering
    \begin{tikzpicture}[
        node distance=2cm,
        box/.style={rectangle, draw, rounded corners, minimum width=2.5cm, minimum height=1cm, align=center},
        arrow/.style={->, >=stealth, thick}
    ]
        % Nodes - customize based on your needs
        \node[box] (input) {Input};
        \node[box, right of=input] (process) {Process};
        \node[box, right of=process] (output) {Output};

        % Arrows
        \draw[arrow] (input) -- (process);
        \draw[arrow] (process) -- (output);
    \end{tikzpicture}
    \caption{CAPTION_PLACEHOLDER}
    \label{fig:LABEL_PLACEHOLDER}
\end{figure}
"""
    elif figure_type == "pgfplots-bar":
        if data:
            lines = data.strip().split("\n")
            headers = lines[0].split(",") if lines else ["Category", "Value"]
            coords = []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) >= 2:
                    coords.append(f"({parts[0]}, {parts[1]})")
            if not coords:
                return "Error: No data rows found. Provide data with at least one data row after the header."
            coords_str = " ".join(coords)
        else:
            headers = ["Category", "Value"]
            coords_str = "(A, 10) (B, 20) (C, 15)"

        xlabel_text = escape_latex(headers[0]) if headers else 'Category'
        ylabel_text = escape_latex(headers[1]) if len(headers) > 1 else 'Value'

        figure_code = rf"""
\begin{{figure}}[htbp]
    \centering
    \begin{{tikzpicture}}
        \begin{{axis}}[
            ybar,
            xlabel={{{xlabel_text}}},
            ylabel={{{ylabel_text}}},
            symbolic x coords={{A, B, C}},
            xtick=data,
            nodes near coords,
            width=0.8\textwidth,
            height=6cm,
        ]
            \addplot coordinates {{{coords_str}}};
        \end{{axis}}
    \end{{tikzpicture}}
    \caption{{CAPTION_PLACEHOLDER}}
    \label{{fig:LABEL_PLACEHOLDER}}
\end{{figure}}
"""
    elif figure_type == "pgfplots-line":
        if data:
            lines = data.strip().split("\n")
            headers = lines[0].split(",") if lines else ["x", "y"]
            coords = []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) >= 2:
                    coords.append(f"({parts[0]}, {parts[1]})")
            if not coords:
                return "Error: No data rows found. Provide data with at least one data row after the header."
            coords_str = " ".join(coords)
        else:
            headers = ["x", "y"]
            coords_str = "(0, 0) (1, 2) (2, 4) (3, 3) (4, 5)"

        xlabel_text = escape_latex(headers[0]) if headers else 'x'
        ylabel_text = escape_latex(headers[1]) if len(headers) > 1 else 'y'

        figure_code = rf"""
\begin{{figure}}[htbp]
    \centering
    \begin{{tikzpicture}}
        \begin{{axis}}[
            xlabel={{{xlabel_text}}},
            ylabel={{{ylabel_text}}},
            legend pos=north west,
            grid=major,
            width=0.8\textwidth,
            height=6cm,
        ]
            \addplot[color=blue, mark=*] coordinates {{{coords_str}}};
            \legend{{Data}}
        \end{{axis}}
    \end{{tikzpicture}}
    \caption{{CAPTION_PLACEHOLDER}}
    \label{{fig:LABEL_PLACEHOLDER}}
\end{{figure}}
"""
    elif figure_type == "pgfplots-scatter":
        coords_str = "(1, 2) (2, 3) (3, 2.5) (4, 4) (5, 4.5)"
        if data:
            lines = data.strip().split("\n")
            coords = []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) >= 2:
                    coords.append(f"({parts[0]}, {parts[1]})")
            if coords:
                coords_str = " ".join(coords)

        figure_code = rf"""
\begin{{figure}}[htbp]
    \centering
    \begin{{tikzpicture}}
        \begin{{axis}}[
            xlabel={{X}},
            ylabel={{Y}},
            only marks,
            width=0.8\textwidth,
            height=6cm,
        ]
            \addplot[color=blue, mark=o] coordinates {{{coords_str}}};
        \end{{axis}}
    \end{{tikzpicture}}
    \caption{{CAPTION_PLACEHOLDER}}
    \label{{fig:LABEL_PLACEHOLDER}}
\end{{figure}}
"""
    else:
        return f"Error: Unknown figure type '{figure_type}'. Use: tikz, pgfplots-bar, pgfplots-line, pgfplots-scatter"

    # Replace placeholders
    if caption:
        figure_code = figure_code.replace("CAPTION_PLACEHOLDER", escape_latex(caption))
    else:
        figure_code = figure_code.replace("CAPTION_PLACEHOLDER", escape_latex(description[:50]))

    if label:
        figure_code = figure_code.replace("LABEL_PLACEHOLDER", label)
    else:
        label_text = re.sub(r"[^a-z0-9]+", "-", description.lower())[:20]
        figure_code = figure_code.replace("LABEL_PLACEHOLDER", label_text)

    return figure_code.strip()


async def create_algorithm(
    ctx: "RunContext[AuraDeps]",
    name: str,
    inputs: str,
    outputs: str,
    steps: str,
    caption: str = "",
    label: str = "",
) -> str:
    """
    Generate an algorithm/pseudocode block.

    Args:
        name: Algorithm name
        inputs: Input parameters (comma-separated)
        outputs: Output values (comma-separated)
        steps: Algorithm steps (one per line, use indentation for nesting)
        caption: Algorithm caption
        label: Label for referencing

    Returns:
        Complete algorithm2e LaTeX code

    Example steps format:
        "Initialize parameters
        for each epoch:
            for each batch:
                Compute loss
                Update weights
        return model"
    """
    def escape_caption(text: str) -> str:
        """Escape caption text (full escaping including $)."""
        replacements = [
            ('\\', r'\textbackslash{}'),
            ('&', r'\&'),
            ('%', r'\%'),
            ('$', r'\$'),
            ('#', r'\#'),
            ('_', r'\_'),
            ('{', r'\{'),
            ('}', r'\}'),
            ('^', r'\^{}'),
            ('~', r'\~{}'),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    # Parse steps and convert to algorithm2e syntax
    step_lines = steps.strip().split("\n")
    step_lines = [l for l in step_lines if l.strip()]
    if not step_lines:
        return "Error: No algorithm steps provided. Please provide at least one step."

    formatted_steps = []

    for line in step_lines:
        stripped = line.lstrip()
        lower = stripped.lower()

        if lower.startswith("for ") and ":" in lower:
            parts = stripped[4:].split(":")
            formatted_steps.append(f"\\For{{{escape_latex_preserve_math(parts[0].strip())}}}")
            formatted_steps.append("{")
        elif lower.startswith("while ") and ":" in lower:
            parts = stripped[6:].split(":")
            formatted_steps.append(f"\\While{{{escape_latex_preserve_math(parts[0].strip())}}}")
            formatted_steps.append("{")
        elif lower.startswith("if ") and ":" in lower:
            parts = stripped[3:].split(":")
            formatted_steps.append(f"\\If{{{escape_latex_preserve_math(parts[0].strip())}}}")
            formatted_steps.append("{")
        elif lower.startswith("else:"):
            formatted_steps.append("}")
            formatted_steps.append("\\Else{")
        elif lower.startswith("return "):
            formatted_steps.append(f"\\Return{{{escape_latex_preserve_math(stripped[7:])}}}")
        elif stripped.endswith(":"):
            formatted_steps.append(f"\\tcp*[l]{{{escape_latex_preserve_math(stripped[:-1])}}}")
        else:
            formatted_steps.append(f"    {escape_latex_preserve_math(stripped)}\\;")

    # Close any open blocks
    open_braces = sum(1 for s in formatted_steps if s == "{") - sum(1 for s in formatted_steps if s == "}")
    formatted_steps.extend(["}"] * open_braces)

    steps_str = "\n        ".join(formatted_steps)

    safe_caption = escape_caption(caption) if caption else escape_caption(name)
    safe_label = label if label else name.lower().replace(' ', '-')
    safe_label = re.sub(r'[^a-z0-9-]', '', safe_label)
    if not safe_label:
        safe_label = "algorithm"

    algorithm_code = rf"""
\begin{{algorithm}}[htbp]
    \caption{{{safe_caption}}}
    \label{{alg:{safe_label}}}
    \KwIn{{{escape_latex_preserve_math(inputs)}}}
    \KwOut{{{escape_latex_preserve_math(outputs)}}}

        {steps_str}
\end{{algorithm}}
"""

    return algorithm_code.strip()


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_latex_tools(agent):
    """
    Register all LaTeX tools with an agent.

    Args:
        agent: PydanticAI Agent instance
    """
    # Compilation tools
    agent.tool(compile_latex)
    agent.tool(check_latex_syntax)

    # Content generation tools
    agent.tool(create_table)
    agent.tool(create_figure)
    agent.tool(create_algorithm)
