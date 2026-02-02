"""
PDF Reader Module

Provides PDF text extraction for academic papers.
Uses PyMuPDF (fitz) for efficient text extraction.

Features:
- Download PDFs from URLs (arXiv, etc.)
- Extract text with page structure
- Handle multi-column layouts
- Cache downloaded PDFs temporarily
"""

import asyncio
import hashlib
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Lazy import fitz to allow module to load even if PyMuPDF not installed
fitz = None


def _get_fitz():
    """Lazy load PyMuPDF."""
    global fitz
    if fitz is None:
        try:
            import fitz as _fitz
            fitz = _fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF is required for PDF reading. "
                "Install with: pip install PyMuPDF"
            )
    return fitz


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PDFPage:
    """Represents a single PDF page."""
    page_number: int
    text: str
    char_count: int


@dataclass
class PDFDocument:
    """Represents an extracted PDF document."""
    title: str
    num_pages: int
    pages: list[PDFPage]
    total_chars: int
    source_url: Optional[str] = None
    arxiv_id: Optional[str] = None

    def get_text(self, max_pages: int = 0, max_chars: int = 0) -> str:
        """
        Get document text with optional limits.

        Args:
            max_pages: Maximum pages to include (0 = all)
            max_chars: Maximum characters to include (0 = all)

        Returns:
            Formatted document text
        """
        lines = [f"# {self.title}", f"Pages: {self.num_pages}", ""]

        total = 0
        pages_to_include = self.pages[:max_pages] if max_pages > 0 else self.pages

        for page in pages_to_include:
            if max_chars > 0 and total >= max_chars:
                break

            page_text = page.text
            if max_chars > 0 and total + len(page_text) > max_chars:
                remaining = max_chars - total
                page_text = page_text[:remaining] + "\n... [truncated]"

            lines.append(f"--- Page {page.page_number} ---")
            lines.append(page_text)
            lines.append("")

            total += len(page_text)

        return "\n".join(lines)


# =============================================================================
# PDF Extraction
# =============================================================================

def extract_text_from_pdf(pdf_path: str | Path) -> PDFDocument:
    """
    Extract text from a PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        PDFDocument with extracted text
    """
    fitz_module = _get_fitz()
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz_module.open(str(pdf_path))

    try:
        # Try to get title from metadata
        metadata = doc.metadata
        title = metadata.get("title", "") if metadata else ""

        # If no title in metadata, use first line of first page
        if not title and doc.page_count > 0:
            first_page_text = doc[0].get_text()
            first_line = first_page_text.split("\n")[0].strip()
            if len(first_line) > 10:
                title = first_line[:100]
            else:
                title = pdf_path.stem

        # Extract text from each page
        pages = []
        total_chars = 0

        for page_num in range(doc.page_count):
            page = doc[page_num]

            # Extract text with better handling of columns
            text = page.get_text("text")

            # Clean up text
            text = _clean_text(text)

            pdf_page = PDFPage(
                page_number=page_num + 1,
                text=text,
                char_count=len(text),
            )
            pages.append(pdf_page)
            total_chars += len(text)

        return PDFDocument(
            title=title,
            num_pages=doc.page_count,
            pages=pages,
            total_chars=total_chars,
        )

    finally:
        doc.close()


def _clean_text(text: str) -> str:
    """Clean extracted PDF text."""
    # Remove excessive whitespace
    text = re.sub(r' +', ' ', text)

    # Remove page headers/footers (common patterns)
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.strip()

        # Skip very short lines that might be page numbers
        if len(line) <= 3 and line.isdigit():
            continue

        # Skip empty lines at start
        if not cleaned_lines and not line:
            continue

        cleaned_lines.append(line)

    # Remove trailing empty lines
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()

    return '\n'.join(cleaned_lines)


# =============================================================================
# arXiv PDF Download
# =============================================================================

ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}.pdf"

# Temporary directory for caching PDFs
_temp_dir: Path | None = None


def _get_temp_dir() -> Path:
    """Get or create temporary directory for PDF cache."""
    global _temp_dir
    if _temp_dir is None or not _temp_dir.exists():
        _temp_dir = Path(tempfile.mkdtemp(prefix="aura_pdf_"))
    return _temp_dir


def _get_cache_path(arxiv_id: str) -> Path:
    """Get cache path for an arXiv paper."""
    # Sanitize ID for filename
    safe_id = arxiv_id.replace("/", "_").replace(":", "_")
    return _get_temp_dir() / f"{safe_id}.pdf"


async def download_arxiv_pdf(
    arxiv_id: str,
    http_client: httpx.AsyncClient,
    use_cache: bool = True,
) -> Path:
    """
    Download PDF from arXiv.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2301.07041" or "cs/0604007")
        http_client: HTTP client for downloading
        use_cache: Whether to use cached PDFs

    Returns:
        Path to downloaded PDF
    """
    # Check cache
    cache_path = _get_cache_path(arxiv_id)
    if use_cache and cache_path.exists():
        logger.info(f"Using cached PDF for {arxiv_id}")
        return cache_path

    # Build URL
    url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    logger.info(f"Downloading PDF from {url}")

    try:
        response = await http_client.get(
            url,
            follow_redirects=True,
            timeout=60.0,
        )
        response.raise_for_status()

        # Verify it's a PDF
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not response.content.startswith(b"%PDF"):
            raise ValueError(f"Response is not a PDF: {content_type}")

        # Save to cache
        cache_path.write_bytes(response.content)
        logger.info(f"Downloaded {len(response.content)} bytes to {cache_path}")

        return cache_path

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise FileNotFoundError(f"arXiv paper not found: {arxiv_id}")
        raise


async def download_pdf_from_url(
    url: str,
    http_client: httpx.AsyncClient,
    use_cache: bool = True,
) -> Path:
    """
    Download PDF from any URL.

    Args:
        url: URL to PDF
        http_client: HTTP client
        use_cache: Whether to cache the download

    Returns:
        Path to downloaded PDF
    """
    # Generate cache key from URL
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    cache_path = _get_temp_dir() / f"url_{url_hash}.pdf"

    if use_cache and cache_path.exists():
        logger.info(f"Using cached PDF for URL")
        return cache_path

    logger.info(f"Downloading PDF from URL")

    response = await http_client.get(
        url,
        follow_redirects=True,
        timeout=60.0,
    )
    response.raise_for_status()

    # Save to cache
    cache_path.write_bytes(response.content)

    return cache_path


# =============================================================================
# High-Level API
# =============================================================================

async def read_arxiv_paper(
    arxiv_id: str,
    http_client: httpx.AsyncClient,
    max_pages: int = 10,
    max_chars: int = 50000,
) -> PDFDocument:
    """
    Download and extract text from an arXiv paper.

    Args:
        arxiv_id: arXiv paper ID
        http_client: HTTP client
        max_pages: Maximum pages to extract (0 = all)
        max_chars: Maximum characters to return

    Returns:
        PDFDocument with extracted text
    """
    pdf_path = await download_arxiv_pdf(arxiv_id, http_client)
    doc = extract_text_from_pdf(pdf_path)
    doc.arxiv_id = arxiv_id
    doc.source_url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)

    return doc


async def read_pdf_from_url(
    url: str,
    http_client: httpx.AsyncClient,
    max_pages: int = 10,
) -> PDFDocument:
    """
    Download and extract text from a PDF URL.

    Args:
        url: URL to PDF
        http_client: HTTP client
        max_pages: Maximum pages to extract

    Returns:
        PDFDocument with extracted text
    """
    pdf_path = await download_pdf_from_url(url, http_client)
    doc = extract_text_from_pdf(pdf_path)
    doc.source_url = url

    return doc


def read_local_pdf(
    pdf_path: str | Path,
    max_pages: int = 10,
) -> PDFDocument:
    """
    Extract text from a local PDF file.

    Args:
        pdf_path: Path to PDF
        max_pages: Maximum pages to extract

    Returns:
        PDFDocument with extracted text
    """
    return extract_text_from_pdf(pdf_path)


# =============================================================================
# Cleanup
# =============================================================================

def clear_pdf_cache():
    """Clear the PDF cache directory."""
    global _temp_dir
    if _temp_dir and _temp_dir.exists():
        import shutil
        shutil.rmtree(_temp_dir, ignore_errors=True)
        _temp_dir = None
        logger.info("Cleared PDF cache")
