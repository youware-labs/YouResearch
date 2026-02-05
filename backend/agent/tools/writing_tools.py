"""
Writing Tools

Tools for document structure analysis and citation management.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic_ai import RunContext

from agent.deps import AuraDeps
from services.latex_parser import (
    parse_document,
    parse_bib_file_path,
    build_section_tree,
    count_citations_per_section,
    find_unused_citations,
    find_missing_citations,
)


async def analyze_structure(
    ctx: "RunContext[AuraDeps]",
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


async def add_citation(
    ctx: "RunContext[AuraDeps]",
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


# =============================================================================
# Helper Functions for Citation Fetching
# =============================================================================

async def _fetch_arxiv_metadata(arxiv_id: str) -> Optional["PaperMetadata"]:
    """Fetch paper metadata from arXiv."""
    import httpx
    import re
    from agent.tools.citations import PaperMetadata

    # Clean ID
    arxiv_id = arxiv_id.split("v")[0]  # Remove version

    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

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
    import re

    encoded_query = urllib.parse.quote(query)
    url = f"https://export.arxiv.org/api/query?search_query=all:{encoded_query}&max_results=1"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()

            content = response.text

            # Extract arXiv ID from first result
            id_match = re.search(r"<id>https?://arxiv.org/abs/([^<]+)</id>", content)
            if not id_match:
                return None

            arxiv_id = id_match.group(1)
            return await _fetch_arxiv_metadata(arxiv_id)
    except Exception:
        return None


# =============================================================================
# Tool Registration Helper
# =============================================================================

def register_writing_tools(agent):
    """
    Register all writing tools with an agent.

    Args:
        agent: PydanticAI Agent instance
    """
    agent.tool(analyze_structure)
    agent.tool(add_citation)
