"""
Semantic Scholar API Client

Enhanced client for Semantic Scholar API with citation graph traversal.
API docs: https://api.semanticscholar.org/api-docs/

Rate limits: 100 requests/sec (unauthenticated), 1 request/sec for bulk endpoints
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

import httpx

logger = logging.getLogger(__name__)


# API Configuration
S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
S2_SEARCH_FIELDS = "paperId,title,authors,abstract,year,citationCount,url,openAccessPdf"
S2_CITATION_FIELDS = "paperId,title,authors,year,citationCount"


@dataclass
class Paper:
    """Represents an academic paper."""
    paper_id: str
    title: str
    authors: list[str]
    year: Optional[int] = None
    abstract: str = ""
    citation_count: int = 0
    url: str = ""
    pdf_url: str = ""
    arxiv_id: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "Paper":
        """Create Paper from S2 API response."""
        authors = [a.get("name", "Unknown") for a in data.get("authors", [])[:5]]
        pdf_url = ""
        if data.get("openAccessPdf"):
            pdf_url = data["openAccessPdf"].get("url", "")

        # Extract arXiv ID if present
        arxiv_id = ""
        external_ids = data.get("externalIds", {})
        if external_ids and isinstance(external_ids, dict):
            arxiv_id = external_ids.get("ArXiv", "")

        return cls(
            paper_id=data.get("paperId", ""),
            title=data.get("title", "Unknown"),
            authors=authors,
            year=data.get("year"),
            abstract=data.get("abstract", "")[:500] if data.get("abstract") else "",
            citation_count=data.get("citationCount", 0),
            url=data.get("url", ""),
            pdf_url=pdf_url,
            arxiv_id=arxiv_id,
        )

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "citation_count": self.citation_count,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "arxiv_id": self.arxiv_id,
        }


@dataclass
class CitationResult:
    """Result from citation/reference traversal."""
    source_paper_id: str
    direction: str  # "citations" or "references"
    papers: list[Paper] = field(default_factory=list)
    total_count: int = 0


class SemanticScholarClient:
    """
    Client for Semantic Scholar API with citation graph support.

    Features:
    - Paper search with relevance ranking
    - Citation graph traversal (who cites this, what this cites)
    - Paper details lookup
    - Rate limiting support
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: Optional[str] = None,
    ):
        self.http_client = http_client
        self.api_key = api_key
        self._request_semaphore = asyncio.Semaphore(10)  # Limit concurrent requests

    def _get_headers(self) -> dict:
        """Get request headers."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    async def search(
        self,
        query: str,
        limit: int = 10,
        year_range: Optional[tuple[int, int]] = None,
    ) -> list[Paper]:
        """
        Search for papers by query.

        Args:
            query: Search query
            limit: Maximum results (1-100)
            year_range: Optional (start_year, end_year) filter

        Returns:
            List of matching papers
        """
        async with self._request_semaphore:
            try:
                params = {
                    "query": query,
                    "limit": min(limit, 100),
                    "fields": S2_SEARCH_FIELDS,
                }

                if year_range:
                    params["year"] = f"{year_range[0]}-{year_range[1]}"

                response = await self.http_client.get(
                    f"{S2_API_BASE}/paper/search",
                    params=params,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 429:
                    logger.warning("Semantic Scholar rate limit hit")
                    await asyncio.sleep(1.0)
                    return []

                response.raise_for_status()
                data = response.json()

                return [Paper.from_api(p) for p in data.get("data", [])]

            except httpx.HTTPStatusError as e:
                logger.error(f"S2 search error: {e}")
                return []
            except Exception as e:
                logger.error(f"S2 search error: {e}")
                return []

    async def get_paper(self, paper_id: str) -> Optional[Paper]:
        """
        Get paper details by ID.

        Args:
            paper_id: Semantic Scholar paper ID or arXiv ID (e.g., "arXiv:2301.07041")

        Returns:
            Paper details or None if not found
        """
        async with self._request_semaphore:
            try:
                response = await self.http_client.get(
                    f"{S2_API_BASE}/paper/{paper_id}",
                    params={"fields": S2_SEARCH_FIELDS},
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return Paper.from_api(response.json())

            except Exception as e:
                logger.error(f"S2 get_paper error: {e}")
                return None

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> CitationResult:
        """
        Get papers that cite this paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum results (1-1000)
            offset: Pagination offset

        Returns:
            CitationResult with citing papers
        """
        return await self._get_connected_papers(
            paper_id, "citations", limit, offset
        )

    async def get_references(
        self,
        paper_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> CitationResult:
        """
        Get papers that this paper cites.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum results (1-1000)
            offset: Pagination offset

        Returns:
            CitationResult with referenced papers
        """
        return await self._get_connected_papers(
            paper_id, "references", limit, offset
        )

    async def _get_connected_papers(
        self,
        paper_id: str,
        direction: Literal["citations", "references"],
        limit: int,
        offset: int,
    ) -> CitationResult:
        """Get papers connected via citations or references."""
        async with self._request_semaphore:
            try:
                response = await self.http_client.get(
                    f"{S2_API_BASE}/paper/{paper_id}/{direction}",
                    params={
                        "fields": S2_CITATION_FIELDS,
                        "limit": min(limit, 1000),
                        "offset": offset,
                    },
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 429:
                    logger.warning("Semantic Scholar rate limit hit")
                    await asyncio.sleep(1.0)
                    return CitationResult(paper_id, direction)

                if response.status_code == 404:
                    return CitationResult(paper_id, direction)

                response.raise_for_status()
                data = response.json()

                # Citations/references are nested under "citingPaper" or "citedPaper"
                key = "citingPaper" if direction == "citations" else "citedPaper"
                papers = []
                items = data.get("data") or []  # Handle null data
                for item in items:
                    paper_data = item.get(key, {})
                    if paper_data and paper_data.get("paperId"):
                        papers.append(Paper.from_api(paper_data))

                return CitationResult(
                    source_paper_id=paper_id,
                    direction=direction,
                    papers=papers,
                    total_count=data.get("total", len(papers)),
                )

            except Exception as e:
                logger.error(f"S2 {direction} error: {e}")
                return CitationResult(paper_id, direction)

    async def explore_citation_graph(
        self,
        paper_id: str,
        direction: Literal["citations", "references", "both"] = "both",
        depth: int = 1,
        max_papers_per_level: int = 20,
    ) -> list[Paper]:
        """
        Explore citation graph starting from a paper.

        Args:
            paper_id: Starting paper ID
            direction: Which direction to explore
            depth: How many levels to traverse (1-2 recommended)
            max_papers_per_level: Max papers per level

        Returns:
            All discovered papers (deduplicated)
        """
        seen_ids: set[str] = {paper_id}
        all_papers: list[Paper] = []
        current_level: list[str] = [paper_id]

        for level in range(depth):
            next_level: list[str] = []

            for pid in current_level[:max_papers_per_level]:
                if direction in ("citations", "both"):
                    result = await self.get_citations(pid, limit=max_papers_per_level)
                    for paper in result.papers:
                        if paper.paper_id not in seen_ids:
                            seen_ids.add(paper.paper_id)
                            all_papers.append(paper)
                            next_level.append(paper.paper_id)

                if direction in ("references", "both"):
                    result = await self.get_references(pid, limit=max_papers_per_level)
                    for paper in result.papers:
                        if paper.paper_id not in seen_ids:
                            seen_ids.add(paper.paper_id)
                            all_papers.append(paper)
                            next_level.append(paper.paper_id)

                # Rate limiting
                await asyncio.sleep(0.1)

            current_level = next_level

        return all_papers

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 20,
    ) -> list[Paper]:
        """
        Search for papers by a specific author.

        Args:
            author_name: Author name to search for
            limit: Maximum results

        Returns:
            List of papers by this author
        """
        async with self._request_semaphore:
            try:
                # First, search for the author
                response = await self.http_client.get(
                    f"{S2_API_BASE}/author/search",
                    params={
                        "query": author_name,
                        "limit": 5,
                    },
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 429:
                    logger.warning("Semantic Scholar rate limit hit")
                    await asyncio.sleep(1.0)
                    return []

                response.raise_for_status()
                data = response.json()

                authors = data.get("data", [])
                if not authors:
                    return []

                # Get the first matching author's papers
                author_id = authors[0].get("authorId")
                if not author_id:
                    return []

                # Get author's papers
                response = await self.http_client.get(
                    f"{S2_API_BASE}/author/{author_id}/papers",
                    params={
                        "fields": S2_SEARCH_FIELDS,
                        "limit": min(limit, 100),
                    },
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                response.raise_for_status()
                data = response.json()

                return [Paper.from_api(p) for p in data.get("data", [])]

            except Exception as e:
                logger.error(f"S2 author search error: {e}")
                return []

    async def get_recommendations(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> list[Paper]:
        """
        Get paper recommendations based on a given paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum results

        Returns:
            List of recommended similar papers
        """
        async with self._request_semaphore:
            try:
                response = await self.http_client.get(
                    f"{S2_API_BASE}/recommendations/v1/papers/forpaper/{paper_id}",
                    params={
                        "fields": S2_SEARCH_FIELDS,
                        "limit": min(limit, 100),
                    },
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code in (404, 429):
                    return []

                response.raise_for_status()
                data = response.json()

                return [Paper.from_api(p) for p in data.get("recommendedPapers", [])]

            except Exception as e:
                logger.error(f"S2 recommendations error: {e}")
                return []

    async def search_top_cited(
        self,
        query: str,
        limit: int = 20,
        min_citations: int = 50,
    ) -> list[Paper]:
        """
        Search for highly-cited papers on a topic.

        Args:
            query: Search query
            limit: Maximum results
            min_citations: Minimum citation count filter

        Returns:
            List of highly-cited papers, sorted by citations
        """
        # Search with a larger limit to filter by citations
        papers = await self.search(query, limit=100)

        # Filter by minimum citations and sort
        cited_papers = [p for p in papers if p.citation_count >= min_citations]
        cited_papers.sort(key=lambda p: p.citation_count, reverse=True)

        return cited_papers[:limit]

    async def search_by_venue(
        self,
        query: str,
        venue: str,
        limit: int = 20,
    ) -> list[Paper]:
        """
        Search for papers from a specific venue (conference/journal).

        Args:
            query: Topic query
            venue: Venue name (e.g., "NeurIPS", "ICML", "Nature")
            limit: Maximum results

        Returns:
            List of papers from that venue
        """
        # Combine query with venue
        combined_query = f"{query} {venue}"
        return await self.search(combined_query, limit=limit)
