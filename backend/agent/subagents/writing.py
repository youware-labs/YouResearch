"""
WritingAgent - Handles complex writing operations.

Delegated from main agent for:
- Style analysis and application
- Consistency checking
- Document refactoring
- Bibliography management
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai import Agent, RunContext

from agent.subagents.base import Subagent, SubagentConfig, register_subagent


logger = logging.getLogger(__name__)


WRITING_SYSTEM_PROMPT = """You are an expert academic writing assistant specialized in LaTeX documents.

Your capabilities:
- Analyze writing style and suggest improvements
- Check for consistency in terminology, notation, and tense
- Manage bibliography (clean unused, deduplicate)
- Suggest claims that need citations
- Refactor document structure

When analyzing text:
1. Be specific with line numbers
2. Provide concrete before/after examples
3. Prioritize issues by impact

When making changes:
1. Preserve existing citations and references
2. Maintain the author's voice
3. Follow academic writing conventions
"""


@dataclass
class WritingDeps:
    """Dependencies for WritingAgent."""

    project_path: str
    http_client: httpx.AsyncClient


@register_subagent("writing")
class WritingAgent(Subagent[WritingDeps]):
    """Agent for complex writing operations."""

    def __init__(self):
        config = SubagentConfig(
            name="writing",
            description="Handles style analysis, consistency checking, and document refactoring",
            max_iterations=10,
            timeout=120.0,
            use_haiku=True,  # Use cheaper model for analysis
        )
        super().__init__(config)
        self._http_client: httpx.AsyncClient | None = None

    @property
    def system_prompt(self) -> str:
        return WRITING_SYSTEM_PROMPT

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    def _create_deps(self, context: dict[str, Any]) -> WritingDeps:
        return WritingDeps(
            project_path=context.get("project_path", ""),
            http_client=self._get_http_client(),
        )

    def _create_agent(self) -> Agent[WritingDeps, str]:
        agent = Agent(
            model=self._get_model(),
            system_prompt=self.system_prompt,
            deps_type=WritingDeps,
            retries=2,
        )

        self._register_tools(agent)
        return agent

    def _register_tools(self, agent: Agent) -> None:
        """Register writing-specific tools."""

        @agent.tool
        async def read_document(
            ctx: RunContext[WritingDeps],
            filepath: str = "main.tex",
        ) -> str:
            """
            Read a LaTeX document for analysis.

            Args:
                filepath: Path relative to project root (default: main.tex)

            Returns:
                File contents with line numbers
            """
            full_path = Path(ctx.deps.project_path) / filepath

            # SECURITY: Path traversal check
            try:
                full_path.resolve().relative_to(Path(ctx.deps.project_path).resolve())
            except ValueError:
                return f"Error: Path must be within project directory: {filepath}"

            if not full_path.exists():
                return f"Error: File not found: {filepath}"

            content = full_path.read_text()
            lines = content.split("\n")
            numbered = [f"{i+1:4}│ {line}" for i, line in enumerate(lines)]
            return "\n".join(numbered)

        @agent.tool
        async def analyze_document_structure(
            ctx: RunContext[WritingDeps],
            filepath: str = "main.tex",
        ) -> str:
            """
            Get document structure for navigation.

            Args:
                filepath: Path relative to project root (default: main.tex)

            Returns:
                Hierarchical section structure with line numbers
            """
            try:
                from services.latex_parser import parse_document, build_section_tree
            except ImportError as e:
                return f"Error: LaTeX parser service not available: {e}"

            full_path = Path(ctx.deps.project_path) / filepath

            # SECURITY: Path traversal check
            try:
                full_path.resolve().relative_to(Path(ctx.deps.project_path).resolve())
            except ValueError:
                return f"Error: Path must be within project directory: {filepath}"

            if not full_path.exists():
                return f"Error: File not found: {filepath}"

            content = full_path.read_text()
            structure = parse_document(content)
            build_section_tree(structure.sections)  # Builds tree in place

            lines = []
            for s in structure.sections:
                indent = "  " * s.level
                lines.append(f"{indent}{s.name} (L{s.line_start}-{s.line_end})")

            if not lines:
                return "No sections found in document"

            return "\n".join(lines)

        @agent.tool
        async def check_consistency(
            ctx: RunContext[WritingDeps],
            filepath: str = "main.tex",
        ) -> str:
            """
            Check for consistency issues in the document.

            Detects:
            - Terminology inconsistencies (e.g., "dataset" vs "data set")
            - Undefined acronyms
            - Common spelling variations

            Args:
                filepath: Path relative to project root (default: main.tex)

            Returns:
                List of consistency issues found
            """
            full_path = Path(ctx.deps.project_path) / filepath

            # SECURITY: Path traversal check
            try:
                full_path.resolve().relative_to(Path(ctx.deps.project_path).resolve())
            except ValueError:
                return f"Error: Path must be within project directory: {filepath}"

            if not full_path.exists():
                return f"Error: File not found: {filepath}"

            content = full_path.read_text()
            lines = content.split("\n")
            issues = []

            # Check common terminology variations
            term_patterns = [
                (r"\bdataset\b", r"\bdata set\b", "dataset/data set"),
                (r"\bdeep learning\b", r"\bdeeplearning\b", "deep learning"),
                (r"\bself-attention\b", r"\bself attention\b", "self-attention/self attention"),
                (r"\bmulti-head\b", r"\bmultihead\b", "multi-head/multihead"),
                (r"\bmulti-task\b", r"\bmultitask\b", "multi-task/multitask"),
                (r"\breal-world\b", r"\breal world\b", "real-world/real world"),
                (r"\bstate-of-the-art\b", r"\bstate of the art\b", "state-of-the-art/state of the art"),
                (r"\bpre-train\b", r"\bpretrain\b", "pre-train/pretrain"),
                (r"\bfine-tune\b", r"\bfinetune\b", "fine-tune/finetune"),
            ]

            for p1, p2, name in term_patterns:
                locs1 = [i + 1 for i, line in enumerate(lines) if re.search(p1, line, re.I)]
                locs2 = [i + 1 for i, line in enumerate(lines) if re.search(p2, line, re.I)]
                if locs1 and locs2:
                    issues.append(
                        f"TERMINOLOGY: '{name}' used inconsistently - "
                        f"variant 1 at L{locs1[:3]}, variant 2 at L{locs2[:3]}"
                    )

            # Check for undefined acronyms (simple heuristic)
            acronyms = re.findall(r"\b([A-Z]{2,})\b", content)
            acronym_counts: dict[str, int] = {}
            for acr in acronyms:
                acronym_counts[acr] = acronym_counts.get(acr, 0) + 1

            for acr, count in acronym_counts.items():
                if count >= 3:
                    # Check if it's defined somewhere (in parentheses)
                    definition_pattern = rf"\([^)]*{acr}[^)]*\)|{acr}\s*\([^)]+\)"
                    if not re.search(definition_pattern, content):
                        first_use = next(
                            (i + 1 for i, line in enumerate(lines) if acr in line),
                            None,
                        )
                        if first_use:
                            issues.append(
                                f"ACRONYM: '{acr}' used {count} times but never defined "
                                f"(first use: L{first_use})"
                            )

            if not issues:
                return "No consistency issues found."

            return "Consistency issues found:\n\n" + "\n".join(f"* {issue}" for issue in issues)

        @agent.tool
        async def clean_bibliography(
            ctx: RunContext[WritingDeps],
            tex_file: str = "main.tex",
        ) -> str:
            """
            Find and report unused bibliography entries.

            Args:
                tex_file: Main tex file to analyze (default: main.tex)

            Returns:
                Analysis of bibliography usage with unused and missing entries
            """
            try:
                from services.latex_parser import (
                    parse_document,
                    parse_bib_file_path,
                    find_unused_citations,
                    find_missing_citations,
                )
            except ImportError as e:
                return f"Error: LaTeX parser service not available: {e}"

            tex_path = Path(ctx.deps.project_path) / tex_file

            # SECURITY: Path traversal check
            try:
                tex_path.resolve().relative_to(Path(ctx.deps.project_path).resolve())
            except ValueError:
                return f"Error: Path must be within project directory: {tex_file}"

            if not tex_path.exists():
                return f"Error: File not found: {tex_file}"

            content = tex_path.read_text()
            structure = parse_document(content)

            if not structure.bib_file:
                return "No bibliography file detected in document"

            bib_path = Path(ctx.deps.project_path) / structure.bib_file
            # SECURITY: Path traversal check for bib file
            try:
                bib_path.resolve().relative_to(Path(ctx.deps.project_path).resolve())
            except ValueError:
                return f"Error: Bibliography path must be within project directory: {structure.bib_file}"
            if not bib_path.exists():
                return f"Bibliography file not found: {structure.bib_file}"

            bib_entries = parse_bib_file_path(bib_path)
            unused = find_unused_citations(structure.citations, bib_entries)
            missing = find_missing_citations(structure.citations, bib_entries)

            lines = [f"Bibliography analysis for {structure.bib_file}:", ""]
            lines.append(f"Total entries: {len(bib_entries)}")
            lines.append(f"Cited in document: {len(structure.citations)}")
            lines.append("")

            if unused:
                lines.append(f"UNUSED ENTRIES ({len(unused)}):")
                for e in unused:
                    title = e.fields.get("title", "No title")[:50]
                    lines.append(f"  * {e.key}: {title}")
                lines.append("")
                lines.append("To remove these, edit the .bib file and delete the unused entries.")
            else:
                lines.append("No unused entries.")

            if missing:
                lines.append("")
                lines.append(f"MISSING FROM BIB ({len(missing)}):")
                for key in missing:
                    lines.append(f"  * {key}")

            return "\n".join(lines)

        @agent.tool
        async def suggest_citations(
            ctx: RunContext[WritingDeps],
            filepath: str = "main.tex",
        ) -> str:
            """
            Find claims that might need citations.

            Detects patterns like:
            - "Studies show..."
            - "Research indicates..."
            - "According to..."
            - Percentage claims without source

            Args:
                filepath: Path relative to project root (default: main.tex)

            Returns:
                List of claims that may need citations
            """
            full_path = Path(ctx.deps.project_path) / filepath

            # SECURITY: Path traversal check
            try:
                full_path.resolve().relative_to(Path(ctx.deps.project_path).resolve())
            except ValueError:
                return f"Error: Path must be within project directory: {filepath}"

            if not full_path.exists():
                return f"Error: File not found: {filepath}"

            content = full_path.read_text()
            lines = content.split("\n")
            suggestions = []

            # Patterns that suggest a claim needs citation
            claim_patterns = [
                (r"studies (show|have shown|indicate|suggest)", "Studies claim"),
                (r"research (shows|has shown|indicates|suggests)", "Research claim"),
                (r"it (has been|is|was) (shown|demonstrated|proven)", "Passive claim"),
                (r"according to (recent )?(research|studies|work)", "Attribution needed"),
                (r"(\d+\.?\d*)\s*%", "Percentage claim"),
                (r"state-of-the-art", "SOTA claim"),
                (r"(recent|previous|prior) work", "Prior work reference"),
                (r"(widely|commonly|generally) (used|accepted|known)", "General claim"),
                (r"(has been|have been) (proposed|developed|introduced)", "Attribution needed"),
            ]

            for i, line in enumerate(lines, start=1):
                # Skip if line already has a citation
                if r"\cite" in line:
                    continue

                # Skip comments and commands
                stripped = line.strip()
                if stripped.startswith("%") or stripped.startswith("\\"):
                    continue

                for pattern, claim_type in claim_patterns:
                    if re.search(pattern, line, re.I):
                        snippet = stripped[:60] + "..." if len(stripped) > 60 else stripped
                        suggestions.append(f"L{i} [{claim_type}]: \"{snippet}\"")
                        break

            if not suggestions:
                return "No claims found that obviously need citations."

            return f"Claims that may need citations ({len(suggestions)}):\n\n" + "\n".join(suggestions)

