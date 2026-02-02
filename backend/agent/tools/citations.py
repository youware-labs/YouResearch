"""
Citation Management Tools

Helpers for generating and managing BibTeX entries.
"""

import re
from dataclasses import dataclass
from typing import Optional


def escape_bibtex(text: str) -> str:
    """Escape BibTeX special characters in text."""
    escapes = [
        ("\\", r"\\"),  # Must be first
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
    ]
    for old, new in escapes:
        text = text.replace(old, new)
    return text


@dataclass
class PaperMetadata:
    """Paper metadata from arXiv or Semantic Scholar."""
    title: str
    authors: list[str]
    year: int
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    venue: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None


def generate_cite_key(paper: PaperMetadata) -> str:
    """
    Generate a citation key from paper metadata.

    Format: {first_author_lastname}{year}{first_significant_word}
    Example: vaswani2017attention
    """
    # Extract first author's last name
    if paper.authors:
        first_author = paper.authors[0]
        # Handle "Last, First" or "First Last" format
        if "," in first_author:
            last_name = first_author.split(",")[0].strip()
        else:
            parts = first_author.split()
            last_name = parts[-1] if parts else "unknown"
    else:
        last_name = "unknown"

    # Clean the last name
    last_name = re.sub(r"[^a-zA-Z]", "", last_name).lower()

    # Extract first significant word from title (skip articles)
    skip_words = {"a", "an", "the", "on", "in", "of", "for", "to", "and", "with"}
    title_words = re.findall(r"[a-zA-Z]+", paper.title.lower())
    first_word = "paper"
    for word in title_words:
        if word not in skip_words and len(word) > 2:
            first_word = word
            break

    return f"{last_name}{paper.year}{first_word}"


def generate_bibtex(
    paper: PaperMetadata,
    cite_key: Optional[str] = None,
) -> str:
    """
    Generate BibTeX entry from paper metadata.

    Determines entry type based on available metadata:
    - @misc for arXiv papers
    - @article for papers with DOI and no venue
    - @inproceedings for papers with venue
    """
    if cite_key is None:
        cite_key = generate_cite_key(paper)

    # Determine entry type
    if paper.arxiv_id:
        entry_type = "misc"
    elif paper.venue:
        entry_type = "inproceedings"
    else:
        entry_type = "article"

    # Build fields
    fields = []

    # Title (escape special chars)
    title = escape_bibtex(paper.title)
    fields.append(f'    title = {{{title}}}')

    # Authors (filter out empty/None values)
    if paper.authors:
        valid_authors = [a for a in paper.authors[:10] if a and a.strip()]
        if valid_authors:
            authors_str = " and ".join(valid_authors)
            if len(paper.authors) > 10:
                authors_str += " and others"
            fields.append(f'    author = {{{authors_str}}}')

    # Year
    fields.append(f'    year = {{{paper.year}}}')

    # arXiv specific
    if paper.arxiv_id:
        fields.append(f'    eprint = {{{paper.arxiv_id}}}')
        fields.append('    archivePrefix = {arXiv}')
        fields.append('    primaryClass = {cs.CL}')  # Default, could be detected

    # Venue
    if paper.venue:
        if entry_type == "inproceedings":
            fields.append(f'    booktitle = {{{paper.venue}}}')
        else:
            fields.append(f'    journal = {{{paper.venue}}}')

    # DOI
    if paper.doi:
        fields.append(f'    doi = {{{paper.doi}}}')

    # URL
    if paper.url:
        fields.append(f'    url = {{{paper.url}}}')

    # Build entry
    fields_str = ",\n".join(fields)
    return f"@{entry_type}{{{cite_key},\n{fields_str}\n}}"


def format_citation_command(
    cite_key: str,
    style: str = "cite",
    prenote: Optional[str] = None,
    postnote: Optional[str] = None,
) -> str:
    r"""
    Format a citation command.

    Examples:
        format_citation_command("vaswani2017") -> r"\cite{vaswani2017}"
        format_citation_command("vaswani2017", "citep", postnote="p. 5") -> r"\citep[p. 5]{vaswani2017}"
    """
    if prenote and postnote:
        return f"\\{style}[{prenote}][{postnote}]{{{cite_key}}}"
    elif postnote:
        return f"\\{style}[{postnote}]{{{cite_key}}}"
    elif prenote:
        return f"\\{style}[{prenote}][]{{{cite_key}}}"
    else:
        return f"\\{style}{{{cite_key}}}"
