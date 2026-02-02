"""
Async Citation API Clients

Async wrappers for citation management tools, optimized for PydanticAI integration.
Uses httpx.AsyncClient for all HTTP operations.
"""

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CitationMetadata:
    """Metadata for a citation."""
    title: str
    authors: list[str]
    year: Optional[int]
    venue: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None
    citation_count: int = 0
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "pmid": self.pmid,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
            "abstract": self.abstract,
            "citation_count": self.citation_count,
            "source": self.source,
        }


# =============================================================================
# PubMed API Client
# =============================================================================

class PubMedClient:
    """Async client for PubMed E-utilities API."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.api_key = os.getenv("NCBI_API_KEY", "")
        self.email = os.getenv("NCBI_EMAIL", "")
        # Rate limiting: 10/sec with key, 3/sec without
        self.delay = 0.11 if self.api_key else 0.34

    async def search(
        self,
        query: str,
        max_results: int = 10,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
    ) -> list[CitationMetadata]:
        """
        Search PubMed for papers.

        Args:
            query: Search query
            max_results: Maximum number of results
            year_start: Filter papers from this year
            year_end: Filter papers until this year

        Returns:
            List of CitationMetadata objects
        """
        # Build query with date filter
        full_query = query
        if year_start or year_end:
            start = year_start or 1900
            end = year_end or 2030
            full_query += f" AND {start}:{end}[Publication Date]"

        # Search for PMIDs
        params = {
            "db": "pubmed",
            "term": full_query,
            "retmax": max_results,
            "retmode": "json",
        }
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = await self.http_client.get(
                f"{self.BASE_URL}esearch.fcgi",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])

            if not pmids:
                return []

            # Fetch metadata for PMIDs
            await asyncio.sleep(self.delay)
            return await self._fetch_metadata(pmids)

        except Exception as e:
            raise RuntimeError(f"PubMed search failed: {e}")

    async def _fetch_metadata(self, pmids: list[str]) -> list[CitationMetadata]:
        """Fetch metadata for a list of PMIDs."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = await self.http_client.get(
                f"{self.BASE_URL}efetch.fcgi",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.text)
            results = []

            for article in root.findall(".//PubmedArticle"):
                metadata = self._parse_article(article)
                if metadata:
                    results.append(metadata)

            return results

        except Exception as e:
            raise RuntimeError(f"PubMed fetch failed: {e}")

    def _parse_article(self, article: ET.Element) -> Optional[CitationMetadata]:
        """Parse a PubmedArticle XML element."""
        try:
            medline = article.find(".//MedlineCitation")
            if medline is None:
                return None

            # PMID
            pmid_elem = medline.find("PMID")
            pmid = pmid_elem.text if pmid_elem is not None else None

            # Article info
            article_elem = medline.find("Article")
            if article_elem is None:
                return None

            # Title
            title_elem = article_elem.find("ArticleTitle")
            title = title_elem.text if title_elem is not None else "Unknown"

            # Authors
            authors = []
            author_list = article_elem.find("AuthorList")
            if author_list is not None:
                for author in author_list.findall("Author"):
                    last = author.find("LastName")
                    first = author.find("ForeName")
                    if last is not None:
                        name = last.text
                        if first is not None:
                            name = f"{last.text}, {first.text}"
                        authors.append(name)

            # Year
            year = None
            pub_date = article_elem.find(".//PubDate")
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                if year_elem is not None:
                    year = int(year_elem.text)

            # Journal
            journal = None
            journal_elem = article_elem.find(".//Journal/Title")
            if journal_elem is not None:
                journal = journal_elem.text

            # Abstract
            abstract = None
            abstract_elem = article_elem.find(".//Abstract/AbstractText")
            if abstract_elem is not None:
                abstract = abstract_elem.text

            # DOI
            doi = None
            for id_elem in article.findall(".//ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = id_elem.text
                    break

            return CitationMetadata(
                title=title,
                authors=authors,
                year=year,
                venue=journal,
                doi=doi,
                pmid=pmid,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                abstract=abstract,
                source="pubmed",
            )

        except Exception:
            return None


# =============================================================================
# CrossRef API Client (for DOI lookup)
# =============================================================================

class CrossRefClient:
    """Async client for CrossRef API (DOI metadata)."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def lookup_doi(self, doi: str) -> Optional[CitationMetadata]:
        """
        Look up metadata for a DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            CitationMetadata or None
        """
        # Clean DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("http://doi.org/"):
            doi = doi[15:]

        try:
            response = await self.http_client.get(
                f"{self.BASE_URL}/{doi}",
                headers={"User-Agent": "Aura/1.0 (Citation Management)"},
                timeout=15.0,
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()
            message = data.get("message", {})

            # Extract authors
            authors = []
            for author in message.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if family:
                    authors.append(f"{family}, {given}".strip(", "))

            # Extract year
            year = None
            if "published-print" in message:
                parts = message["published-print"].get("date-parts", [[]])
                if parts and parts[0]:
                    year = parts[0][0]
            elif "published-online" in message:
                parts = message["published-online"].get("date-parts", [[]])
                if parts and parts[0]:
                    year = parts[0][0]
            elif "created" in message:
                parts = message["created"].get("date-parts", [[]])
                if parts and parts[0]:
                    year = parts[0][0]

            # Extract title
            title = message.get("title", ["Unknown"])[0]

            # Extract venue
            venue = None
            if message.get("container-title"):
                venue = message["container-title"][0]

            return CitationMetadata(
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                doi=doi,
                url=f"https://doi.org/{doi}",
                source="crossref",
            )

        except Exception as e:
            raise RuntimeError(f"CrossRef lookup failed for {doi}: {e}")


# =============================================================================
# Google Scholar Client (direct scraping)
# =============================================================================

class GoogleScholarClient:
    """Client for Google Scholar using direct HTTP requests."""

    # Rate limiting: track last request time
    _last_request_time: float = 0
    _min_request_interval: float = 2.0  # Minimum 2 seconds between requests

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def search(
        self,
        query: str,
        max_results: int = 10,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
    ) -> list[CitationMetadata]:
        """
        Search Google Scholar.

        Args:
            query: Search query
            max_results: Maximum number of results
            year_start: Filter papers from this year
            year_end: Filter papers until this year

        Returns:
            List of CitationMetadata objects
        """
        import asyncio
        import time

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("beautifulsoup4 required. Install with: pip install beautifulsoup4")

        # Rate limiting: wait if needed
        current_time = time.time()
        time_since_last = current_time - GoogleScholarClient._last_request_time
        if time_since_last < GoogleScholarClient._min_request_interval:
            wait_time = GoogleScholarClient._min_request_interval - time_since_last
            await asyncio.sleep(wait_time)
        GoogleScholarClient._last_request_time = time.time()

        # Build URL with year filters
        url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}&hl=en"
        if year_start:
            url += f"&as_ylo={year_start}"
        if year_end:
            url += f"&as_yhi={year_end}"

        try:
            response = await self.http_client.get(
                url,
                headers=self.headers,
                follow_redirects=True,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise RuntimeError(f"Google Scholar returned {response.status_code}")

            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            # Check for CAPTCHA or rate limiting
            articles = soup.select(".gs_ri")
            if not articles:
                # Log the page content for debugging
                import logging
                logger = logging.getLogger(__name__)

                # Check for common blocking patterns
                if "unusual traffic" in response.text.lower() or "captcha" in response.text.lower():
                    logger.warning("Google Scholar CAPTCHA detected - try again later")
                    raise RuntimeError("Google Scholar is showing a CAPTCHA. Try again in a few minutes.")
                elif "did not match any articles" in response.text.lower():
                    logger.info(f"No results found for query: {query}")
                    return []
                else:
                    logger.warning(f"No articles found in Google Scholar response. Page length: {len(response.text)}")
                    # Log first 500 chars for debugging
                    logger.debug(f"Response preview: {response.text[:500]}")

            for article in articles[:max_results]:
                metadata = self._parse_article(article)
                if metadata:
                    results.append(metadata)

            return results

        except Exception as e:
            raise RuntimeError(f"Google Scholar search failed: {e}")

    def _parse_article(self, article) -> Optional[CitationMetadata]:
        """Parse a Google Scholar article element."""
        import re

        try:
            # Title
            title_elem = article.select_one(".gs_rt")
            if not title_elem:
                return None

            title = title_elem.get_text()
            # Remove [PDF] [HTML] etc prefixes
            title = re.sub(r"^\[.*?\]\s*", "", title).strip()

            # Get link - ensure it's an absolute URL
            link_elem = title_elem.select_one("a")
            url = None
            if link_elem:
                href = link_elem.get("href")
                if href:
                    # Skip Google Scholar redirect links, get actual paper links
                    if href.startswith("/scholar"):
                        # This is a relative Google Scholar link, skip it
                        url = None
                    elif href.startswith("http"):
                        url = href
                    elif href.startswith("//"):
                        url = "https:" + href

            # Authors/Year line: "A Vaswani, N Shazeer... - NIPS, 2017 - site.com"
            info_elem = article.select_one(".gs_a")
            info_text = info_elem.get_text() if info_elem else ""

            authors = []
            year = None
            venue = None

            if info_text:
                # Parse info line
                parts = info_text.split(" - ")
                if len(parts) >= 1:
                    # Authors part
                    author_str = parts[0]
                    authors = [a.strip() for a in author_str.split(",")]
                    # Remove "..." from last author
                    if authors and authors[-1].endswith("…"):
                        authors[-1] = authors[-1].rstrip("…").strip()

                if len(parts) >= 2:
                    # Venue/year part
                    venue_year = parts[1]
                    year_match = re.search(r"\b(19|20)\d{2}\b", venue_year)
                    if year_match:
                        year = int(year_match.group())
                    venue = venue_year.split(",")[0].strip() if "," in venue_year else venue_year.strip()

            # Citations count
            citation_count = 0
            cited_elem = article.select_one(".gs_fl a")
            if cited_elem:
                cited_text = cited_elem.get_text()
                cited_match = re.search(r"Cited by (\d+)", cited_text)
                if cited_match:
                    citation_count = int(cited_match.group(1))

            # Abstract snippet
            abstract_elem = article.select_one(".gs_rs")
            abstract = abstract_elem.get_text() if abstract_elem else None

            return CitationMetadata(
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                url=url,
                abstract=abstract,
                citation_count=citation_count,
                source="google_scholar",
            )

        except Exception:
            return None


# =============================================================================
# Unified Metadata Extractor
# =============================================================================

class MetadataExtractor:
    """Extract metadata from various identifier types."""

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.crossref = CrossRefClient(http_client)
        self.pubmed = PubMedClient(http_client)

    def identify_type(self, identifier: str) -> tuple[str, str]:
        """
        Identify the type of identifier.

        Returns:
            Tuple of (type, cleaned_identifier)
        """
        identifier = identifier.strip()

        # URL handling
        if identifier.startswith("http://") or identifier.startswith("https://"):
            return self._parse_url(identifier)

        # DOI
        if identifier.startswith("10."):
            return ("doi", identifier)

        # arXiv ID
        if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", identifier):
            return ("arxiv", identifier)
        if identifier.lower().startswith("arxiv:"):
            return ("arxiv", identifier[6:])

        # PMID (8+ digit number)
        if identifier.isdigit() and len(identifier) >= 7:
            return ("pmid", identifier)

        # PMCID
        if identifier.upper().startswith("PMC") and identifier[3:].isdigit():
            return ("pmcid", identifier.upper())

        return ("unknown", identifier)

    def _parse_url(self, url: str) -> tuple[str, str]:
        """Parse URL to extract identifier."""
        parsed = urlparse(url)

        # DOI URLs
        if "doi.org" in parsed.netloc:
            doi = parsed.path.lstrip("/")
            return ("doi", doi)

        # PubMed URLs
        if "pubmed.ncbi.nlm.nih.gov" in parsed.netloc:
            pmid = re.search(r"/(\d+)", parsed.path)
            if pmid:
                return ("pmid", pmid.group(1))

        # arXiv URLs
        if "arxiv.org" in parsed.netloc:
            arxiv_id = re.search(r"/abs/(\d{4}\.\d{4,5})", parsed.path)
            if arxiv_id:
                return ("arxiv", arxiv_id.group(1))

        return ("url", url)

    async def extract(self, identifier: str) -> Optional[CitationMetadata]:
        """
        Extract metadata from any supported identifier.

        Args:
            identifier: DOI, PMID, arXiv ID, or URL

        Returns:
            CitationMetadata or None
        """
        id_type, cleaned_id = self.identify_type(identifier)

        if id_type == "doi":
            return await self.crossref.lookup_doi(cleaned_id)
        elif id_type == "pmid":
            results = await self.pubmed._fetch_metadata([cleaned_id])
            return results[0] if results else None
        elif id_type == "arxiv":
            # Use arXiv API (already exists in research.py)
            return None  # Let search_arxiv handle this
        else:
            return None


# =============================================================================
# OpenAlex API Client (free, no rate limits)
# =============================================================================

class OpenAlexClient:
    """Async client for OpenAlex API - free, no rate limits, excellent coverage."""

    BASE_URL = "https://api.openalex.org"

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[CitationMetadata]:
        """
        Search OpenAlex for papers.

        Args:
            query: Search query (title or keywords)
            max_results: Maximum number of results

        Returns:
            List of CitationMetadata objects
        """
        try:
            params = {
                "search": query,
                "per_page": max_results,
                "mailto": "aura@example.com",  # Polite pool
            }

            response = await self.http_client.get(
                f"{self.BASE_URL}/works",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for work in data.get("results", []):
                metadata = self._parse_work(work)
                if metadata:
                    results.append(metadata)

            return results

        except Exception as e:
            raise RuntimeError(f"OpenAlex search failed: {e}")

    def _parse_work(self, work: dict) -> Optional[CitationMetadata]:
        """Parse an OpenAlex work object."""
        try:
            # Title
            title = work.get("title", "Unknown")
            if not title:
                return None

            # Authors
            authors = []
            for authorship in work.get("authorships", [])[:10]:
                author = authorship.get("author", {})
                name = author.get("display_name", "")
                if name:
                    authors.append(name)

            # Year
            year = work.get("publication_year")

            # Venue
            venue = None
            primary_location = work.get("primary_location", {}) or {}
            source = primary_location.get("source", {}) or {}
            if source:
                venue = source.get("display_name")

            # DOI
            doi = work.get("doi", "")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi[16:]

            # Abstract (OpenAlex stores inverted index)
            abstract = None
            abstract_index = work.get("abstract_inverted_index")
            if abstract_index:
                # Reconstruct abstract from inverted index
                word_positions = []
                for word, positions in abstract_index.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(word for _, word in word_positions)

            return CitationMetadata(
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                doi=doi if doi else None,
                url=work.get("id", ""),
                abstract=abstract,
                citation_count=work.get("cited_by_count", 0),
                source="openalex",
            )

        except Exception:
            return None


# =============================================================================
# Formatting Helpers
# =============================================================================

def format_results(
    results: list[CitationMetadata],
    query: str,
    source: str,
) -> str:
    """Format search results for display."""
    if not results:
        return f"No papers found on {source} for query: '{query}'"

    lines = [f"Found {len(results)} papers on {source} for '{query}':\n"]

    for i, paper in enumerate(results, 1):
        # Authors
        authors_str = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_str += " et al."

        # Title (plain text)
        lines.append(f"{i}. **{paper.title}**")
        lines.append(f"   Authors: {authors_str}")

        if paper.year:
            lines.append(f"   Year: {paper.year}")

        if paper.venue:
            lines.append(f"   Venue: {paper.venue}")

        if paper.citation_count > 0:
            lines.append(f"   Citations: {paper.citation_count}")

        # URL on separate line (clickable)
        if paper.url:
            lines.append(f"   Link: {paper.url}")

        if paper.doi:
            lines.append(f"   DOI: https://doi.org/{paper.doi}")

        if paper.abstract:
            abstract = paper.abstract[:300]
            if len(paper.abstract) > 300:
                abstract += "..."
            lines.append(f"   Abstract: {abstract}")

        lines.append("")

    return "\n".join(lines)
