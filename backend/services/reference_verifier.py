"""
Reference Verification Service

Verifies that bibliography entries are real papers with correct metadata
and are cited in appropriate context.
"""

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

import httpx
from openai import AsyncOpenAI

from services.latex_parser import BibEntry
from services.semantic_scholar import Paper, SemanticScholarClient
from agent.tools.citation_management.citation_api import (
    CrossRefClient,
    PubMedClient,
    CitationMetadata,
    MetadataExtractor,
    OpenAlexClient,
    GoogleScholarClient,
)


# Citation patterns (same as latex_parser but we need the positions)
CITATION_COMMANDS = [
    "cite", "citep", "citet", "citeauthor", "citeyear",
    "autocite", "textcite", "parencite", "footcite",
    "fullcite", "nocite",
]
CITATION_REGEX = re.compile(
    r"\\(" + "|".join(CITATION_COMMANDS) + r")\{([^}]+)\}"
)


@dataclass
class CitationContext:
    """A citation usage in the document."""
    cite_key: str
    line_number: int
    surrounding_text: str  # ~200 chars around \cite{}
    claim: str  # Extracted claim being made (text before citation)


@dataclass
class VerificationResult:
    """Result of verifying a single citation."""
    cite_key: str
    status: Literal["verified", "warning", "error", "pending"]

    # Existence check
    exists: bool = False
    matched_paper: Optional[dict] = None  # Paper.to_dict() from Semantic Scholar

    # Metadata check
    metadata_issues: list[str] = field(default_factory=list)

    # Context check
    context_score: float = 0.0  # 0-1 confidence
    context_explanation: str = ""
    checked_via: Literal["abstract", "pdf", "skipped", "failed"] = "skipped"

    # Original data
    bib_entry: Optional[dict] = None  # BibEntry as dict
    usages: list[CitationContext] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "cite_key": self.cite_key,
            "status": self.status,
            "exists": self.exists,
            "matched_paper": self.matched_paper,
            "metadata_issues": self.metadata_issues,
            "context_score": self.context_score,
            "context_explanation": self.context_explanation,
            "checked_via": self.checked_via,
            "bib_entry": self.bib_entry,
            "usages": [
                {
                    "cite_key": u.cite_key,
                    "line_number": u.line_number,
                    "surrounding_text": u.surrounding_text,
                    "claim": u.claim,
                }
                for u in self.usages
            ],
        }


def extract_citation_contexts(
    tex_content: str,
    cite_key: str,
    context_chars: int = 200,
) -> list[CitationContext]:
    """
    Find all usages of a citation and extract surrounding context.

    Args:
        tex_content: Full LaTeX document content
        cite_key: The citation key to find
        context_chars: Characters to extract around each citation

    Returns:
        List of CitationContext for each usage
    """
    lines = tex_content.split("\n")
    contexts: list[CitationContext] = []

    for line_num, line in enumerate(lines, start=1):
        for match in CITATION_REGEX.finditer(line):
            keys_str = match.group(2)
            keys = [k.strip() for k in keys_str.split(",")]

            if cite_key not in keys:
                continue

            # Get position in line
            cite_start = match.start()

            # Extract claim (text before the citation on this line and previous lines)
            claim_text = line[:cite_start].strip()

            # If claim is short, include previous line
            if len(claim_text) < 50 and line_num > 1:
                prev_line = lines[line_num - 2].strip()
                claim_text = prev_line + " " + claim_text

            # Clean up the claim
            claim_text = claim_text.strip()
            if claim_text.endswith(","):
                claim_text = claim_text[:-1]

            # Get surrounding context (before and after)
            line_start = max(0, cite_start - context_chars // 2)
            line_end = min(len(line), match.end() + context_chars // 2)
            surrounding = line[line_start:line_end]

            contexts.append(CitationContext(
                cite_key=cite_key,
                line_number=line_num,
                surrounding_text=surrounding,
                claim=claim_text[-200:] if len(claim_text) > 200 else claim_text,
            ))

    return contexts


async def lookup_paper(
    bib_entry: BibEntry,
    http_client: httpx.AsyncClient,
) -> tuple[bool, Optional[Paper], list[str]]:
    """
    Look up a paper using multiple sources for better accuracy.

    Tries in order:
    1. DOI lookup via CrossRef (most reliable)
    2. arXiv ID lookup via Semantic Scholar
    3. Title search via PubMed (good for medical/bio papers)
    4. Title search via Semantic Scholar (fallback)

    Returns:
        (exists, matched_paper, metadata_issues)
    """
    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    fields = bib_entry.fields
    metadata_issues: list[str] = []

    # Try DOI first via CrossRef (most reliable)
    doi = fields.get("doi", "")
    if doi:
        try:
            crossref = CrossRefClient(http_client)
            citation = await crossref.lookup_doi(doi)
            if citation:
                paper = _citation_to_paper(citation)
                issues = _compare_metadata(bib_entry, paper)
                return True, paper, issues
        except Exception as e:
            logger.debug(f"CrossRef lookup failed for {doi}: {e}")

    # Try Semantic Scholar for arXiv papers
    arxiv_id = fields.get("eprint", "") or fields.get("arxiv", "")
    if arxiv_id:
        try:
            await asyncio.sleep(0.5)  # Rate limiting
            s2_client = SemanticScholarClient(http_client)
            arxiv_clean = re.sub(r"v\d+$", "", arxiv_id)
            paper = await s2_client.get_paper(f"arXiv:{arxiv_clean}")
            if paper:
                issues = _compare_metadata(bib_entry, paper)
                return True, paper, issues
        except Exception as e:
            logger.debug(f"S2 arXiv lookup failed for {arxiv_id}: {e}")

    # Try title search via Google Scholar first (best coverage)
    title = fields.get("title", "")
    if title:
        clean_title = re.sub(r"[{}]", "", title).strip()

        try:
            gs = GoogleScholarClient(http_client)
            results = await gs.search(clean_title, max_results=5)
            for citation in results:
                if _titles_match(clean_title, citation.title):
                    paper = _citation_to_paper(citation)
                    issues = _compare_metadata(bib_entry, paper)
                    return True, paper, issues
        except Exception as e:
            logger.debug(f"Google Scholar search failed for {clean_title[:30]}: {e}")

        # Fall back to OpenAlex (free, no rate limits)
        try:
            openalex = OpenAlexClient(http_client)
            results = await openalex.search(clean_title, max_results=5)
            for citation in results:
                if _titles_match(clean_title, citation.title):
                    paper = _citation_to_paper(citation)
                    issues = _compare_metadata(bib_entry, paper)
                    return True, paper, issues
        except Exception as e:
            logger.debug(f"OpenAlex search failed for {clean_title[:30]}: {e}")

        # Try PubMed for medical/bio papers
        try:
            pubmed = PubMedClient(http_client)
            results = await pubmed.search(clean_title, max_results=3)
            for citation in results:
                if _titles_match(clean_title, citation.title):
                    paper = _citation_to_paper(citation)
                    issues = _compare_metadata(bib_entry, paper)
                    return True, paper, issues
        except Exception as e:
            logger.debug(f"PubMed search failed for {clean_title[:30]}: {e}")

        # Fall back to Semantic Scholar title search
        try:
            await asyncio.sleep(1.0)  # Rate limiting - S2 has strict limits
            s2_client = SemanticScholarClient(http_client)
            papers = await s2_client.search(clean_title, limit=5)
            for paper in papers:
                if _titles_match(clean_title, paper.title):
                    issues = _compare_metadata(bib_entry, paper)
                    return True, paper, issues
        except Exception as e:
            logger.debug(f"S2 title search failed for {clean_title[:30]}: {e}")

    return False, None, ["Paper not found in Google Scholar, OpenAlex, CrossRef, PubMed, or Semantic Scholar"]


def _citation_to_paper(citation: CitationMetadata) -> Paper:
    """Convert CitationMetadata to Paper object for compatibility."""
    return Paper(
        paper_id=citation.doi or citation.pmid or "",
        title=citation.title,
        authors=citation.authors,
        year=citation.year,
        abstract=citation.abstract or "",
        citation_count=citation.citation_count,
        url=citation.url or "",
    )


def _titles_match(bib_title: str, paper_title: str, threshold: float = 0.7) -> bool:
    """
    Check if titles match using word overlap.

    Handles cases where:
    - Bib title is a prefix of the full paper title
    - Titles have punctuation variations
    """
    # Clean punctuation and split into words
    import string
    translator = str.maketrans(string.punctuation, ' ' * len(string.punctuation))

    bib_clean = bib_title.lower().translate(translator)
    paper_clean = paper_title.lower().translate(translator)

    bib_words = set(bib_clean.split())
    paper_words = set(paper_clean.split())

    # Remove common stopwords
    stopwords = {"a", "an", "the", "of", "in", "on", "for", "to", "and", "with", "from"}
    bib_words -= stopwords
    paper_words -= stopwords

    if not bib_words or not paper_words:
        return False

    # Check if bib title is a subset of paper title (prefix match)
    if bib_words <= paper_words:
        return True

    # Fall back to overlap ratio using smaller set as denominator
    # This handles cases where bib has shorter title
    overlap = len(bib_words & paper_words)
    min_len = min(len(bib_words), len(paper_words))

    return overlap / min_len >= threshold


def _compare_metadata(bib_entry: BibEntry, paper: Paper) -> list[str]:
    """Compare bib entry metadata with found paper."""
    issues: list[str] = []
    fields = bib_entry.fields

    # Check year
    bib_year = fields.get("year", "")
    if bib_year and paper.year:
        try:
            if int(bib_year) != paper.year:
                issues.append(f"Year mismatch: bib says {bib_year}, found {paper.year}")
        except ValueError:
            pass

    # Check title similarity
    bib_title = re.sub(r"[{}]", "", fields.get("title", "")).strip().lower()
    paper_title = paper.title.lower()
    if bib_title and paper_title:
        if not _titles_match(bib_title, paper_title, threshold=0.7):
            issues.append(f"Title mismatch: '{bib_title[:50]}...' vs '{paper_title[:50]}...'")

    return issues


CONTEXT_VALIDATION_PROMPT = """Given this claim from a paper:
"{claim}"

And this abstract from the cited paper "{title}":
"{abstract}"

Does the abstract support this claim? Respond with exactly one of:
- SUPPORTED: The abstract clearly supports this claim
- PLAUSIBLE: The abstract is related but doesn't directly confirm
- UNSUPPORTED: The abstract contradicts or doesn't relate to this claim
- UNCERTAIN: Cannot determine from abstract alone

Then add a one-sentence explanation on the next line."""


async def validate_context(
    claim: str,
    paper_title: str,
    paper_abstract: str,
    llm_client: AsyncOpenAI,
    model_name: str = "anthropic/claude-3.5-haiku",
) -> tuple[float, str, str]:
    """
    Validate if a claim is supported by a paper's abstract.

    Returns:
        (score, explanation, verdict)
        - score: 0.0-1.0 confidence
        - explanation: Why it matches/doesn't
        - verdict: SUPPORTED/PLAUSIBLE/UNSUPPORTED/UNCERTAIN
    """
    if not claim or not paper_abstract:
        return 0.5, "No claim or abstract to validate", "UNCERTAIN"

    prompt = CONTEXT_VALIDATION_PROMPT.format(
        claim=claim[:500],
        title=paper_title,
        abstract=paper_abstract[:1000],
    )

    try:
        response = await llm_client.chat.completions.create(
            model=model_name,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.choices[0].message.content.strip()

        lines = result.split("\n", 1)
        verdict = lines[0].strip().upper()
        explanation = lines[1].strip() if len(lines) > 1 else ""

        # Map verdict to score
        score_map = {
            "SUPPORTED": 0.9,
            "PLAUSIBLE": 0.6,
            "UNSUPPORTED": 0.2,
            "UNCERTAIN": 0.5,
        }

        # Extract verdict from response (might have extra text)
        for v in score_map:
            if v in verdict:
                return score_map[v], explanation, v

        return 0.5, explanation or result, "UNCERTAIN"

    except Exception as e:
        return 0.5, f"Validation failed: {str(e)}", "UNCERTAIN"


# =============================================================================
# Main Verifier Class
# =============================================================================

from pathlib import Path
from typing import AsyncGenerator
import logging

from services.latex_parser import parse_bib_file_path

logger = logging.getLogger(__name__)


class ReferenceVerifier:
    """
    Orchestrates reference verification for a LaTeX project.

    Verification steps:
    1. Parse .bib file to get all entries
    2. Parse .tex file(s) to find citation usages
    3. For each citation:
       a. Look up paper in Semantic Scholar
       b. Compare metadata
       c. Validate context claims
    """

    def __init__(
        self,
        project_path: str,
        http_client: httpx.AsyncClient,
        llm_client: AsyncOpenAI,
        bib_file: Optional[str] = None,
        model_name: str = "anthropic/claude-3.5-haiku",
    ):
        self.project_path = Path(project_path)
        self.http_client = http_client
        self.llm_client = llm_client
        self.bib_file = bib_file  # Specific bib file to use
        self.model_name = model_name

    def _find_bib_file(self) -> Optional[Path]:
        """Find the .bib file in the project."""
        # If a specific bib file was provided, use it
        if self.bib_file:
            bib_path = Path(self.bib_file)
            if bib_path.is_absolute():
                return bib_path if bib_path.exists() else None
            else:
                full_path = self.project_path / bib_path
                return full_path if full_path.exists() else None

        # Otherwise, search for .bib files recursively
        bib_files = list(self.project_path.glob("**/*.bib"))
        if bib_files:
            return bib_files[0]
        return None

    def _find_tex_files(self) -> list[Path]:
        """Find all .tex files in the project."""
        return list(self.project_path.glob("**/*.tex"))

    async def verify_all(self) -> AsyncGenerator[VerificationResult, None]:
        """
        Verify all citations in the project.

        Yields VerificationResult for each citation as verification completes.
        """
        # Find bib file
        bib_path = self._find_bib_file()
        if not bib_path:
            logger.warning("No .bib file found")
            return

        # Parse bib entries
        bib_entries = parse_bib_file_path(bib_path)
        if not bib_entries:
            logger.warning("No entries in .bib file")
            return

        # Read all tex content
        tex_content = ""
        for tex_path in self._find_tex_files():
            try:
                tex_content += tex_path.read_text(encoding="utf-8", errors="replace")
                tex_content += "\n"
            except Exception as e:
                logger.error(f"Failed to read {tex_path}: {e}")

        # Verify each entry
        for entry in bib_entries:
            result = await self._verify_entry(entry, tex_content)
            yield result

    async def _verify_entry(
        self,
        entry: BibEntry,
        tex_content: str,
    ) -> VerificationResult:
        """Verify a single bibliography entry."""
        cite_key = entry.key

        # Extract usage contexts
        usages = extract_citation_contexts(tex_content, cite_key)

        # Look up paper
        exists, paper, metadata_issues = await lookup_paper(entry, self.http_client)

        if not exists:
            return VerificationResult(
                cite_key=cite_key,
                status="error",
                exists=False,
                metadata_issues=metadata_issues,
                bib_entry={"key": entry.key, "fields": entry.fields},
                usages=usages,
            )

        # Validate context if we have usages and abstract
        context_score = 0.0
        context_explanation = ""
        checked_via = "skipped"

        if usages and paper and paper.abstract:
            # Use first usage for context validation
            first_claim = usages[0].claim
            if first_claim:
                context_score, context_explanation, verdict = await validate_context(
                    claim=first_claim,
                    paper_title=paper.title,
                    paper_abstract=paper.abstract,
                    llm_client=self.llm_client,
                    model_name=self.model_name,
                )
                checked_via = "abstract"

        # Determine status
        if metadata_issues:
            status = "warning"
        elif context_score < 0.4:
            status = "warning"
        else:
            status = "verified"

        return VerificationResult(
            cite_key=cite_key,
            status=status,
            exists=True,
            matched_paper=paper.to_dict() if paper else None,
            metadata_issues=metadata_issues,
            context_score=context_score,
            context_explanation=context_explanation,
            checked_via=checked_via,
            bib_entry={"key": entry.key, "fields": entry.fields},
            usages=usages,
        )