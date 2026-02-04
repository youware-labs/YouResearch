"""
PydanticAI-based Aura Agent

Main agent implementation using PydanticAI framework.
Replaces the raw Anthropic SDK implementation.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from pydantic_ai import Agent, RunContext

from agent.providers import get_default_model
from agent.prompts import get_system_prompt
from agent.processors import default_history_processor

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agent.hitl import HITLManager, ApprovalStatus
    from agent.planning import PlanManager, Plan

from services.latex_parser import (
    parse_document,
    parse_bib_file_path,
    build_section_tree,
    count_citations_per_section,
    find_unused_citations,
    find_missing_citations,
    DocumentStructure,
)


@dataclass
class AuraDeps:
    """
    Dependencies injected into agent tools.

    These are passed to every tool call via RunContext.
    """
    project_path: str
    project_name: str = ""

    # HITL support (optional)
    hitl_manager: Optional["HITLManager"] = None

    # Planning support (optional)
    plan_manager: Optional["PlanManager"] = None
    session_id: str = "default"

    # Provider info (for prompt adjustments)
    provider_name: str = "openrouter"

    def __post_init__(self):
        if not self.project_name and self.project_path:
            self.project_name = Path(self.project_path).name


async def _check_hitl(
    ctx: RunContext[AuraDeps],
    tool_name: str,
    tool_args: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """
    Check HITL approval for a tool call.

    Returns:
        (should_proceed, rejection_message, modified_args)
    """
    hitl_manager = ctx.deps.hitl_manager

    # Debug logging
    logger.info(f"HITL check for {tool_name}: manager={hitl_manager}, needs_approval={hitl_manager.needs_approval(tool_name) if hitl_manager else 'N/A'}")

    if not hitl_manager or not hitl_manager.needs_approval(tool_name):
        return True, None, None

    from agent.hitl import ApprovalStatus
    import uuid

    logger.info(f"Requesting approval for {tool_name}")

    # Request approval
    approval = await hitl_manager.request_approval(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_call_id=str(uuid.uuid4()),
    )

    logger.info(f"Approval result: {approval.status}")

    if approval.status == ApprovalStatus.REJECTED:
        return False, f"Operation cancelled: {approval.rejection_reason}", None

    if approval.status == ApprovalStatus.TIMEOUT:
        return False, "Operation cancelled: Approval timeout", None

    # Return modified args if user edited them
    modified = approval.modified_args if approval.status == ApprovalStatus.MODIFIED else None
    return True, None, modified


# Create the main Aura agent
aura_agent = Agent(
    model=get_default_model(),
    deps_type=AuraDeps,
    retries=3,
    instructions=get_system_prompt,  # Dynamic instructions based on RunContext
    history_processors=[default_history_processor],  # Clean up message history
)


# =============================================================================
# File Tools
# =============================================================================

@aura_agent.tool
async def read_file(ctx: RunContext[AuraDeps], filepath: str) -> str:
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


@aura_agent.tool
async def edit_file(
    ctx: RunContext[AuraDeps],
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
    # HITL check - wait for approval if enabled
    should_proceed, rejection_msg, modified_args = await _check_hitl(
        ctx, "edit_file",
        {"filepath": filepath, "old_string": old_string, "new_string": new_string}
    )
    if not should_proceed:
        return rejection_msg

    # Use modified args if user edited them
    if modified_args:
        filepath = modified_args.get("filepath", filepath)
        old_string = modified_args.get("old_string", old_string)
        new_string = modified_args.get("new_string", new_string)

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


@aura_agent.tool
async def write_file(
    ctx: RunContext[AuraDeps],
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
    # HITL check - wait for approval if enabled
    should_proceed, rejection_msg, modified_args = await _check_hitl(
        ctx, "write_file",
        {"filepath": filepath, "content": content}
    )
    if not should_proceed:
        return rejection_msg

    # Use modified args if user edited them
    if modified_args:
        filepath = modified_args.get("filepath", filepath)
        if "content" in modified_args:
            content = modified_args["content"]

    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    # Security: ensure path is within project
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        return f"Error: Path escapes project directory: {filepath}"

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return f"Successfully wrote {filepath} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing file: {e}"


@aura_agent.tool
async def list_files(ctx: RunContext[AuraDeps], directory: str = ".") -> str:
    """
    List files in a directory.

    Args:
        directory: Directory relative to project root (default: root)

    Returns:
        List of files and directories
    """
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / directory

    if not full_path.exists():
        return f"Error: Directory not found: {directory}"

    if not full_path.is_dir():
        return f"Error: Not a directory: {directory}"

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

        return f"Contents of {directory}:\n" + "\n".join(items) if items else f"Directory {directory} is empty"
    except Exception as e:
        return f"Error listing directory: {e}"


@aura_agent.tool
async def find_files(ctx: RunContext[AuraDeps], pattern: str) -> str:
    """
    Find files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*.tex", "**/*.bib")

    Returns:
        List of matching files
    """
    project_path = Path(ctx.deps.project_path)

    try:
        matches = list(project_path.glob(pattern))
        if not matches:
            return f"No files found matching: {pattern}"

        # Make paths relative and sort
        relative = sorted([str(m.relative_to(project_path)) for m in matches if m.is_file()])
        return f"Found {len(relative)} files matching '{pattern}':\n" + "\n".join(f"  {f}" for f in relative[:50])
    except Exception as e:
        return f"Error searching files: {e}"


@aura_agent.tool
async def search_in_file(
    ctx: RunContext[AuraDeps],
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
    import re

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


@aura_agent.tool
async def read_file_lines(
    ctx: RunContext[AuraDeps],
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


# =============================================================================
# Document Analysis Tools
# =============================================================================

@aura_agent.tool
async def analyze_structure(
    ctx: RunContext[AuraDeps],
    filepath: str = "main.tex",
) -> str:
    """
    Analyze the structure of a LaTeX document.

    Returns section hierarchy, figures/tables, citation statistics,
    and any structural issues detected.

    Args:
        filepath: Path to the .tex file to analyze (default: main.tex)

    Returns:
        Formatted structure analysis with sections, elements, and issues
    """
    from pathlib import Path

    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    if not full_path.exists():
        return f"Error: File not found: {filepath}"

    # Security check: ensure path is within project directory
    try:
        full_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        return f"Error: Path must be within project directory: {filepath}"

    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
        structure = parse_document(content)
        tree = build_section_tree(structure.sections)
        cite_counts = count_citations_per_section(structure, content)

        # Format output
        lines = [f"Document Structure: {filepath}", ""]

        # Section hierarchy
        lines.append("SECTIONS:")
        def format_tree(sections, prefix=""):
            result = []
            for i, s in enumerate(sections):
                is_last = i == len(sections) - 1
                current_prefix = "└── " if is_last else "├── "
                cite_count = cite_counts.get(s.name, 0)
                label_info = f" [{s.label}]" if s.label else ""
                result.append(f"{prefix}{current_prefix}{s.name} (L{s.line_start}-{s.line_end}) [{cite_count} citations]{label_info}")
                if s.children:
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    result.extend(format_tree(s.children, child_prefix))
            return result

        lines.extend(format_tree(tree))
        lines.append("")

        # Elements
        lines.append("ELEMENTS:")
        if structure.elements:
            for e in structure.elements:
                label_status = "✓ labeled" if e.label else "⚠ no label"
                caption_preview = e.caption[:40] + "..." if e.caption and len(e.caption) > 40 else (e.caption or "no caption")
                lines.append(f"  - {e.type}: \"{caption_preview}\" (L{e.line_start}) {label_status}")
        else:
            lines.append("  (none found)")
        lines.append("")

        # Citation info
        lines.append(f"CITATIONS: {len(structure.citations)} unique keys")
        lines.append(f"STYLE: {structure.citation_style}")
        lines.append(f"BIB FILE: {structure.bib_file or 'not detected'}")
        lines.append(f"PACKAGES: {', '.join(structure.packages[:10])}")
        lines.append("")

        # Issues
        issues = []

        # Check for sections without citations in expected places
        for s in structure.sections:
            name_lower = s.name.lower()
            if "related" in name_lower or "background" in name_lower:
                if cite_counts.get(s.name, 0) < 3:
                    issues.append(f"Section '{s.name}' has few citations ({cite_counts.get(s.name, 0)}) - expected more for this section type")

        # Check for unlabeled figures/tables
        unlabeled = [e for e in structure.elements if not e.label]
        if unlabeled:
            issues.append(f"{len(unlabeled)} element(s) missing \\label{{}}")

        # Check bib file if available
        if structure.bib_file:
            bib_path = Path(project_path) / structure.bib_file
            if bib_path.exists():
                bib_entries = parse_bib_file_path(bib_path)
                unused = find_unused_citations(structure.citations, bib_entries)
                missing = find_missing_citations(structure.citations, bib_entries)
                if unused:
                    issues.append(f"{len(unused)} unused entries in bibliography")
                if missing:
                    issues.append(f"{len(missing)} citations not in bibliography: {', '.join(missing[:5])}")

        if issues:
            lines.append("ISSUES:")
            for issue in issues:
                lines.append(f"  ⚠ {issue}")
        else:
            lines.append("ISSUES: None detected ✓")

        return "\n".join(lines)

    except Exception as e:
        return f"Error analyzing document: {e}"


@aura_agent.tool
async def add_citation(
    ctx: RunContext[AuraDeps],
    paper_id: str,
    cite_key: Optional[str] = None,
    insert_after_line: Optional[int] = None,
    cite_style: str = "cite",
) -> str:
    """
    Add a citation to the document.

    Fetches paper metadata, generates BibTeX entry, adds to .bib file,
    and optionally inserts the citation command in the document.

    Args:
        paper_id: Paper identifier - can be:
                  - arXiv ID (e.g., "2301.07041" or "arxiv:2301.07041")
                  - Semantic Scholar ID (e.g., "s2:abc123")
                  - Search query (will search and use first result)
        cite_key: Optional custom citation key (auto-generated if not provided)
        insert_after_line: Line number after which to insert \\cite{} command
        cite_style: Citation style - "cite", "citep", "citet", "autocite", etc.

    Returns:
        Confirmation with the cite key and BibTeX entry
    """
    from pathlib import Path
    import httpx
    from agent.tools.citations import PaperMetadata, generate_bibtex, generate_cite_key, format_citation_command

    project_path = ctx.deps.project_path

    # Determine paper source and fetch metadata
    paper = None

    if paper_id.startswith("arxiv:") or paper_id.replace(".", "").replace("v", "").isdigit():
        # arXiv paper
        arxiv_id = paper_id.replace("arxiv:", "").strip()
        paper = await _fetch_arxiv_metadata(arxiv_id)
    elif paper_id.startswith("s2:"):
        # Semantic Scholar ID
        s2_id = paper_id.replace("s2:", "").strip()
        paper = await _fetch_s2_metadata(s2_id)
    else:
        # Treat as search query - search arXiv
        paper = await _search_arxiv_for_paper(paper_id)

    if not paper:
        return f"Error: Could not find paper: {paper_id}"

    # Generate cite key if not provided
    if cite_key is None:
        cite_key = generate_cite_key(paper)

    # Generate BibTeX entry
    bibtex = generate_bibtex(paper, cite_key)

    # Find and update .bib file
    main_tex = Path(project_path) / "main.tex"
    if main_tex.exists():
        content = main_tex.read_text()
        structure = parse_document(content)
        bib_file = structure.bib_file or "refs.bib"
    else:
        bib_file = "refs.bib"

    bib_path = Path(project_path) / bib_file

    # Security check: ensure bib path is within project directory
    try:
        bib_path.resolve().relative_to(Path(project_path).resolve())
    except ValueError:
        return f"Error: Bibliography path must be within project directory: {bib_file}"

    # Check if entry already exists
    if bib_path.exists():
        existing_content = bib_path.read_text()
        if cite_key in existing_content:
            return f"Citation key '{cite_key}' already exists in {bib_file}. Use a different cite_key."
        # Append entry
        with open(bib_path, "a") as f:
            f.write("\n\n" + bibtex)
    else:
        # Create new .bib file
        bib_path.write_text(bibtex + "\n")

    result = f"Added citation to {bib_file}:\n\n{bibtex}\n\nUse: {format_citation_command(cite_key, cite_style)}"

    # Insert citation in document if requested
    if insert_after_line is not None and main_tex.exists():
        content = main_tex.read_text()
        lines = content.split("\n")
        if 0 < insert_after_line <= len(lines):
            cite_cmd = format_citation_command(cite_key, cite_style)
            lines[insert_after_line - 1] += f" {cite_cmd}"
            main_tex.write_text("\n".join(lines))
            result += f"\n\nInserted {cite_cmd} after line {insert_after_line}"

    return result


async def _fetch_arxiv_metadata(arxiv_id: str) -> Optional["PaperMetadata"]:
    """Fetch paper metadata from arXiv."""
    import httpx
    from agent.tools.citations import PaperMetadata

    # Clean ID
    arxiv_id = arxiv_id.split("v")[0]  # Remove version

    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            # Parse Atom XML (simple regex extraction)
            import re
            content = response.text

            title_match = re.search(r"<title>([^<]+)</title>", content)
            if not title_match or "Error" in title_match.group(1):
                return None

            title = title_match.group(1).strip().replace("\n", " ")

            # Extract authors
            authors = re.findall(r"<name>([^<]+)</name>", content)

            # Extract year from published date
            pub_match = re.search(r"<published>(\d{4})", content)
            year = int(pub_match.group(1)) if pub_match else 2024

            # Extract abstract
            abs_match = re.search(r"<summary>([^<]+)</summary>", content, re.DOTALL)
            abstract = abs_match.group(1).strip() if abs_match else None

            return PaperMetadata(
                title=title,
                authors=authors[:10],
                year=year,
                arxiv_id=arxiv_id,
                abstract=abstract,
                url=f"https://arxiv.org/abs/{arxiv_id}",
            )
    except Exception:
        return None


async def _fetch_s2_metadata(s2_id: str) -> Optional["PaperMetadata"]:
    """Fetch paper metadata from Semantic Scholar."""
    import httpx
    from agent.tools.citations import PaperMetadata

    url = f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}"
    params = {"fields": "title,authors,year,abstract,externalIds,venue"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

            return PaperMetadata(
                title=data.get("title", "Unknown"),
                authors=[a.get("name", "") for a in data.get("authors", [])[:10]],
                year=data.get("year", 2024),
                arxiv_id=data.get("externalIds", {}).get("ArXiv"),
                doi=data.get("externalIds", {}).get("DOI"),
                venue=data.get("venue"),
                abstract=data.get("abstract"),
            )
    except Exception:
        return None


async def _search_arxiv_for_paper(query: str) -> Optional["PaperMetadata"]:
    """Search arXiv and return first result."""
    import httpx
    import urllib.parse

    encoded_query = urllib.parse.quote(query)
    url = f"https://export.arxiv.org/api/query?search_query=all:{encoded_query}&max_results=1"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            import re
            content = response.text

            # Extract arXiv ID from first result
            id_match = re.search(r"<id>https?://arxiv.org/abs/([^<]+)</id>", content)
            if not id_match:
                return None

            arxiv_id = id_match.group(1)
            return await _fetch_arxiv_metadata(arxiv_id)
    except Exception:
        return None


@aura_agent.tool
async def create_table(
    ctx: RunContext[AuraDeps],
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
    import re

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
                # Check if it's a number (including decimals, percentages)
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
            # Pad row if needed (create copy to avoid mutation)
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
            # Pad row if needed (create copy to avoid mutation)
            padded_row = row + [''] * (num_cols - len(row))
            row_str = " & ".join(escape_latex(cell) for cell in padded_row)
            table_lines.append(f"        {row_str} \\\\")
            table_lines.append(r"        \hline")

        table_lines.extend([
            r"    \end{tabular}",
            r"\end{table}",
        ])

    return "\n".join(table_lines)


@aura_agent.tool
async def create_figure(
    ctx: RunContext[AuraDeps],
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
    import re

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

    # For complex figure generation, we provide templates
    # The LLM will customize based on description

    if figure_type == "tikz":
        # Generic TikZ template
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
        # Parse data for bar chart
        if data:
            lines = data.strip().split("\n")
            headers = lines[0].split(",") if lines else ["Category", "Value"]

            coords = []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) >= 2:
                    coords.append(f"({parts[0]}, {parts[1]})")

            # Validate that we have data rows
            if not coords:
                return "Error: No data rows found. Provide data with at least one data row after the header."

            coords_str = " ".join(coords)
        else:
            headers = ["Category", "Value"]
            coords_str = "(A, 10) (B, 20) (C, 15)"

        # Escape LaTeX special characters in axis labels
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
        # Parse data for line plot
        if data:
            lines = data.strip().split("\n")
            headers = lines[0].split(",") if lines else ["x", "y"]

            coords = []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) >= 2:
                    coords.append(f"({parts[0]}, {parts[1]})")

            # Validate that we have data rows
            if not coords:
                return "Error: No data rows found. Provide data with at least one data row after the header."

            coords_str = " ".join(coords)
        else:
            headers = ["x", "y"]
            coords_str = "(0, 0) (1, 2) (2, 4) (3, 3) (4, 5)"

        # Escape LaTeX special characters in axis labels
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
        # Generate label from description
        label_text = re.sub(r"[^a-z0-9]+", "-", description.lower())[:20]
        figure_code = figure_code.replace("LABEL_PLACEHOLDER", label_text)

    return figure_code.strip()


@aura_agent.tool
async def create_algorithm(
    ctx: RunContext[AuraDeps],
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
    import re

    def escape_latex(text: str) -> str:
        """Escape LaTeX special characters in text (preserves math mode)."""
        # Don't escape text inside math mode ($...$)
        # Split by math mode delimiters and only escape non-math parts
        parts = re.split(r'(\$[^$]+\$)', text)
        escaped_parts = []
        for part in parts:
            if part.startswith('$') and part.endswith('$'):
                # Math mode - don't escape
                escaped_parts.append(part)
            else:
                # Regular text - escape special characters
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
    # Filter out empty lines early and validate
    step_lines = [l for l in step_lines if l.strip()]
    if not step_lines:
        return "Error: No algorithm steps provided. Please provide at least one step."

    formatted_steps = []

    for line in step_lines:
        # Count leading spaces/tabs for indentation level
        stripped = line.lstrip()

        indent = len(line) - len(stripped)
        indent_level = indent // 4  # Assume 4 spaces per level

        # Convert common patterns to algorithm2e commands
        lower = stripped.lower()

        if lower.startswith("for ") and ":" in lower:
            # for X in Y: or for each X:
            parts = stripped[4:].split(":")
            formatted_steps.append(f"\\For{{{escape_latex(parts[0].strip())}}}")
            formatted_steps.append("{")
        elif lower.startswith("while ") and ":" in lower:
            parts = stripped[6:].split(":")
            formatted_steps.append(f"\\While{{{escape_latex(parts[0].strip())}}}")
            formatted_steps.append("{")
        elif lower.startswith("if ") and ":" in lower:
            parts = stripped[3:].split(":")
            formatted_steps.append(f"\\If{{{escape_latex(parts[0].strip())}}}")
            formatted_steps.append("{")
        elif lower.startswith("else:"):
            formatted_steps.append("}")
            formatted_steps.append("\\Else{")
        elif lower.startswith("return "):
            formatted_steps.append(f"\\Return{{{escape_latex(stripped[7:])}}}")
        elif stripped.endswith(":"):
            # Generic block start
            formatted_steps.append(f"\\tcp*[l]{{{escape_latex(stripped[:-1])}}}")
        else:
            # Regular statement
            formatted_steps.append(f"    {escape_latex(stripped)}\\;")

    # Close any open blocks (simple heuristic)
    open_braces = sum(1 for s in formatted_steps if s == "{") - sum(1 for s in formatted_steps if s == "}")
    formatted_steps.extend(["}"] * open_braces)

    steps_str = "\n        ".join(formatted_steps)

    # Escape caption and name for safe LaTeX output
    safe_caption = escape_caption(caption) if caption else escape_caption(name)
    safe_label = label if label else name.lower().replace(' ', '-')
    # Remove invalid characters (only allow alphanumeric and hyphens)
    safe_label = re.sub(r'[^a-z0-9-]', '', safe_label)
    # Ensure not empty after sanitization
    if not safe_label:
        safe_label = "algorithm"

    algorithm_code = rf"""
\begin{{algorithm}}[htbp]
    \caption{{{safe_caption}}}
    \label{{alg:{safe_label}}}
    \KwIn{{{escape_latex(inputs)}}}
    \KwOut{{{escape_latex(outputs)}}}

        {steps_str}
\end{{algorithm}}
"""

    return algorithm_code.strip()


# =============================================================================
# PDF Tools
# =============================================================================

@aura_agent.tool
async def read_pdf(
    ctx: RunContext[AuraDeps],
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


# =============================================================================
# LaTeX Tools
# =============================================================================

@aura_agent.tool
async def compile_latex(
    ctx: RunContext[AuraDeps],
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
    from services.unified_latex import get_unified_latex

    latex = get_unified_latex()
    project_path = ctx.deps.project_path

    result = await latex.compile(project_path, main_file)

    if result.success:
        backend_info = f" (using {result.backend_used})" if result.backend_used else ""
        return f"Compilation successful{backend_info}! Output: {result.pdf_path}"
    elif result.tex_not_available:
        return f"No LaTeX compiler available:\n{result.error_summary}"
    else:
        # Return last 2000 chars of log
        log_excerpt = result.log[-2000:] if result.log else ""
        return f"Compilation failed:\n{result.error_summary or ''}\n{log_excerpt}"


@aura_agent.tool
async def check_latex_syntax(
    ctx: RunContext[AuraDeps],
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
    project_path = ctx.deps.project_path
    full_path = Path(project_path) / filepath

    if not full_path.exists():
        return f"Error: File not found: {filepath}"

    try:
        content = full_path.read_text()
        issues = []

        # Check for unmatched braces
        brace_count = content.count('{') - content.count('}')
        if brace_count != 0:
            issues.append(f"Unmatched braces: {'+' if brace_count > 0 else ''}{brace_count}")

        # Check for unmatched environments
        import re
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
            return f"Found {len(issues)} potential issues in {filepath}:\n" + "\n".join(f"  - {i}" for i in issues)
        else:
            return f"No syntax issues found in {filepath}"
    except Exception as e:
        return f"Error checking syntax: {e}"


# =============================================================================
# Thinking Tool
# =============================================================================

@aura_agent.tool
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
# Subagent Delegation
# =============================================================================

@aura_agent.tool
async def delegate_to_subagent(
    ctx: RunContext[AuraDeps],
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
    from agent.subagents import get_subagent, list_subagents
    from agent.venue_hitl import get_research_preference_manager

    # Validate subagent name
    available = list_subagents()
    available_names = [s["name"] for s in available]

    if subagent not in available_names:
        return f"Unknown subagent: '{subagent}'. Available: {', '.join(available_names)}"

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
            return f"[{subagent.upper()} AGENT RESULT]\n\n{result.output}"
        else:
            return f"[{subagent.upper()} AGENT ERROR]\n\n{result.error}: {result.output}"

    except Exception as e:
        return f"Subagent error: {str(e)}"


# =============================================================================
# Planning Tools
# =============================================================================

@aura_agent.tool
async def plan_task(
    ctx: RunContext[AuraDeps],
    task_description: str,
) -> str:
    """
    Create a structured plan for a complex task.

    Use this BEFORE starting any complex task that involves:
    - Multiple file changes
    - Several sequential steps
    - Refactoring or restructuring
    - Adding new features
    - Any task you're unsure how to approach

    The planner will analyze the task and create a step-by-step plan.

    Args:
        task_description: Detailed description of what you need to accomplish

    Returns:
        The created plan in markdown format, or error message
    """
    from agent.subagents.planner import create_plan_for_task
    from agent.planning import get_plan_manager

    try:
        # Create the plan using PlannerAgent
        plan = await create_plan_for_task(
            task=task_description,
            project_path=ctx.deps.project_path,
            project_name=ctx.deps.project_name,
        )

        if not plan:
            return f"""Error: Failed to create plan.

This can happen if:
1. The project path doesn't exist or has no files
2. The task description is unclear

Project path: {ctx.deps.project_path}

Try providing more specific details about what you want to accomplish, or proceed without a formal plan by breaking down the task yourself."""

        # Store the plan in the manager
        plan_manager = ctx.deps.plan_manager or get_plan_manager()
        session_id = ctx.deps.session_id
        project_path = ctx.deps.project_path

        # Register the plan
        await plan_manager.create_plan(
            goal=plan.goal,
            original_request=task_description,
            steps=[s.to_dict() for s in plan.steps],
            session_id=session_id,
            project_path=project_path,
            context=plan.context,
            complexity=plan.complexity,
            estimated_files=plan.estimated_files,
            risks=plan.risks,
            assumptions=plan.assumptions,
        )

        # Return the plan in markdown format
        return f"""# Plan Created Successfully

{plan.to_markdown()}

---

**Next Steps:**
1. Review the plan above
2. Use `get_current_plan` to see the plan at any time
3. Use `start_plan_execution` when ready to begin
4. Use `complete_plan_step` after finishing each step
"""

    except Exception as e:
        return f"Planning error: {str(e)}"


@aura_agent.tool
async def get_current_plan(ctx: RunContext[AuraDeps]) -> str:
    """
    View the current plan and its progress.

    Use this to:
    - See what steps remain
    - Check progress on the plan
    - Review the overall goal

    Returns:
        Current plan in markdown format, or message if no plan exists
    """
    from agent.planning import get_plan_manager

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan. Use `plan_task` to create one."

    return plan.to_markdown()


@aura_agent.tool
async def start_plan_execution(ctx: RunContext[AuraDeps]) -> str:
    """
    Start executing the current plan.

    This marks the plan as in-progress and returns the first step to work on.

    Returns:
        First step to execute, or error if no plan exists
    """
    from agent.planning import get_plan_manager, PlanStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan. Use `plan_task` to create one first."

    if plan.status not in [PlanStatus.DRAFT, PlanStatus.APPROVED]:
        return f"Plan is already {plan.status.value}. Cannot start."

    # Approve and start
    await plan_manager.approve_plan(session_id, project_path=project_path)

    # Get first step
    step = await plan_manager.start_next_step(session_id, project_path=project_path)

    if not step:
        return "No steps to execute in this plan."

    return f"""# Starting Plan Execution

**Now working on Step {step.step_number}: {step.title}**

{step.description}

Files: {', '.join(step.files) if step.files else 'None specified'}
Verification: {step.verification or 'None specified'}

---

After completing this step, use `complete_plan_step` with a summary of what you did.
If this step fails, use `fail_plan_step` with the error.
"""


@aura_agent.tool
async def complete_plan_step(
    ctx: RunContext[AuraDeps],
    summary: str,
) -> str:
    """
    Mark the current plan step as completed and move to the next.

    Call this after successfully completing a step in the plan.

    Args:
        summary: Brief summary of what was accomplished

    Returns:
        Next step to work on, or completion message
    """
    from agent.planning import get_plan_manager, StepStatus, PlanStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan."

    current = plan.current_step
    if not current:
        return "No step currently in progress."

    # Complete the current step
    await plan_manager.complete_current_step(summary, session_id, project_path=project_path)

    # Refresh plan
    plan = await plan_manager.get_plan(session_id)

    # Check if plan is complete
    if plan.status == PlanStatus.COMPLETED:
        return f"""# Plan Completed! ✅

All {len(plan.steps)} steps have been completed.

**Summary:**
{chr(10).join(f'- Step {s.step_number}: {s.title} ✅' for s in plan.steps)}

The task "{plan.goal}" has been accomplished.
"""

    # Start next step
    next_step = await plan_manager.start_next_step(session_id, project_path=project_path)

    if not next_step:
        progress = plan.progress
        return f"""Step completed, but no more steps available.

Progress: {progress['completed']}/{progress['total']} steps completed
Remaining pending: {progress['pending']}

Check the plan with `get_current_plan` for details.
"""

    return f"""# Step Completed ✅

**Completed:** {current.title}
Summary: {summary}

---

**Now working on Step {next_step.step_number}: {next_step.title}**

{next_step.description}

Files: {', '.join(next_step.files) if next_step.files else 'None specified'}
Verification: {next_step.verification or 'None specified'}
"""


@aura_agent.tool
async def fail_plan_step(
    ctx: RunContext[AuraDeps],
    error: str,
) -> str:
    """
    Mark the current plan step as failed.

    Use this when a step cannot be completed due to an error.

    Args:
        error: Description of what went wrong

    Returns:
        Status update and options for proceeding
    """
    from agent.planning import get_plan_manager, StepStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan."

    current = plan.current_step
    if not current:
        return "No step currently in progress."

    # Mark as failed
    await plan_manager.fail_current_step(error, session_id, project_path=project_path)

    return f"""# Step Failed ❌

**Failed:** Step {current.step_number}: {current.title}
Error: {error}

---

**Options:**
1. Try to fix the issue and retry by using `start_plan_execution` again
2. Skip this step with `skip_plan_step` and continue
3. Abandon the plan with `abandon_plan`

Use `get_current_plan` to see the full plan status.
"""


@aura_agent.tool
async def skip_plan_step(
    ctx: RunContext[AuraDeps],
    reason: str,
) -> str:
    """
    Skip the current plan step and move to the next.

    Use this when a step is not needed or should be skipped.

    Args:
        reason: Why this step is being skipped

    Returns:
        Next step to work on
    """
    from agent.planning import get_plan_manager, StepStatus

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan."

    current = plan.current_step
    if not current:
        return "No step currently in progress."

    # Mark as skipped
    await plan_manager.update_step(
        current.step_id, StepStatus.SKIPPED, reason, session_id=session_id, project_path=project_path
    )

    # Get next step
    next_step = await plan_manager.start_next_step(session_id, project_path=project_path)

    if not next_step:
        return f"Step skipped. No more steps available. Use `get_current_plan` to see status."

    return f"""# Step Skipped ⏭️

**Skipped:** {current.title}
Reason: {reason}

---

**Now working on Step {next_step.step_number}: {next_step.title}**

{next_step.description}
"""


@aura_agent.tool
async def abandon_plan(ctx: RunContext[AuraDeps]) -> str:
    """
    Abandon the current plan.

    Use this to cancel the current plan and start fresh.

    Returns:
        Confirmation message
    """
    from agent.planning import get_plan_manager

    plan_manager = ctx.deps.plan_manager or get_plan_manager()
    session_id = ctx.deps.session_id
    project_path = ctx.deps.project_path

    plan = await plan_manager.get_plan(session_id)

    if not plan:
        return "No active plan to abandon."

    await plan_manager.cancel_plan(session_id, project_path=project_path)

    return f"""# Plan Abandoned

The plan "{plan.goal}" has been cancelled.

Progress at time of abandonment:
- Completed: {plan.progress['completed']} steps
- Failed: {plan.progress['failed']} steps
- Pending: {plan.progress['pending']} steps

You can create a new plan with `plan_task`.
"""
