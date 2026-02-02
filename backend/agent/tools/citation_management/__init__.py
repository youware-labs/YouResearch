"""
Citation Management Tools

Tools for searching, extracting, validating, and formatting citations.
Downloaded from: https://github.com/benchflow-ai/skillsbench

Available scripts:
- doi_to_bibtex.py: Convert DOIs to BibTeX format
- extract_metadata.py: Extract metadata from DOI, PubMed, arXiv
- search_google_scholar.py: Search Google Scholar
- search_pubmed.py: Search PubMed
- validate_citations.py: Validate BibTeX citations
- format_bibtex.py: Format and clean BibTeX files
"""

from pathlib import Path

SKILL_DIR = Path(__file__).parent
SCRIPTS_DIR = SKILL_DIR
ASSETS_DIR = SKILL_DIR / "assets"
REFERENCES_DIR = SKILL_DIR / "references"
