"""
Research Subagent

Specialized agent for academic research tasks with two modes:
- CHAT mode: Quick searches, paper summaries, single-turn help
- VIBE mode: Deep autonomous research with hypothesis generation

IMPORTANT: This agent NEVER makes up citations. It only reports real papers
found through the APIs.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from xml.etree import ElementTree

import httpx
from pydantic_ai import Agent, RunContext

from agent.subagents.base import (
    Subagent,
    SubagentConfig,
    SubagentResult,
    register_subagent,
)
from agent.providers import get_haiku_model
from agent.vibe_state import VibeResearchState, ResearchPhase
from agent.tools.citation_management.citation_api import (
    PubMedClient,
    GoogleScholarClient,
    MetadataExtractor,
    format_results,
)
from services.semantic_scholar import SemanticScholarClient

logger = logging.getLogger(__name__)


# =============================================================================
# Mode and Dependencies
# =============================================================================

class ResearchMode(str, Enum):
    """Mode of operation for research agent."""
    CHAT = "chat"   # Quick, single-turn research help
    VIBE = "vibe"   # Deep autonomous research workflow


@dataclass
class CollectedPaper:
    """A paper collected from search results."""
    title: str
    url: str
    authors: str = ""
    year: int | None = None


@dataclass
class ResearchDeps:
    """Dependencies for the research agent."""
    # HTTP client for API calls
    http_client: httpx.AsyncClient

    # Mode of operation
    mode: ResearchMode = ResearchMode.CHAT

    # Limit results
    max_results: int = 10

    # Research domain (e.g., "Computer Science", "Physiology")
    domain: str = ""

    # Venue/conference filter (optional)
    venue_filter: list[str] = field(default_factory=list)

    # Whether venue preferences have been asked
    venue_preferences_asked: bool = False

    # Vibe mode only
    project_path: str = ""
    vibe_state: VibeResearchState | None = None

    # Collected papers with links (appended to final output)
    collected_papers: list[CollectedPaper] = field(default_factory=list)


# =============================================================================
# arXiv API
# =============================================================================

ARXIV_API_URL = "https://export.arxiv.org/api/query"


async def search_web_for_papers(
    query: str,
    http_client: httpx.AsyncClient,
    max_results: int = 10,
) -> list[dict]:
    """
    Search the web for academic papers using DuckDuckGo.

    Searches Google Scholar, ACM, IEEE, PubMed, and other sources.

    Args:
        query: Search query
        http_client: HTTP client (unused, kept for API compatibility)
        max_results: Maximum number of results

    Returns:
        List of paper dictionaries with title, url, snippet, source
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _sync_search():
        from ddgs import DDGS

        results = []
        try:
            # Search with academic keywords to focus on papers
            enhanced_query = f"{query} paper pdf"

            with DDGS(timeout=20) as ddgs:
                for r in ddgs.text(enhanced_query, max_results=max_results * 2):
                    url = r.get("href", "")
                    title = r.get("title", "")
                    snippet = r.get("body", "")

                    # Skip non-paper results
                    if not url or not title:
                        continue
                    if len(title) < 10:
                        continue

                    # Determine source from URL
                    source = "web"
                    url_lower = url.lower()
                    if "arxiv.org" in url_lower:
                        source = "arxiv"
                    elif "scholar.google" in url_lower:
                        source = "google_scholar"
                    elif "acm.org" in url_lower or "dl.acm.org" in url_lower:
                        source = "acm"
                    elif "ieee.org" in url_lower or "ieeexplore" in url_lower:
                        source = "ieee"
                    elif "pubmed" in url_lower or "ncbi.nlm.nih.gov" in url_lower:
                        source = "pubmed"
                    elif "openreview.net" in url_lower:
                        source = "openreview"
                    elif "semanticscholar.org" in url_lower:
                        source = "semantic_scholar"
                    elif "researchgate.net" in url_lower:
                        source = "researchgate"
                    elif "springer" in url_lower:
                        source = "springer"
                    elif "sciencedirect" in url_lower or "elsevier" in url_lower:
                        source = "elsevier"

                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet[:500] if snippet else "",
                        "source": source,
                    })

                    if len(results) >= max_results:
                        break

        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise

        return results

    # Run synchronous search in thread pool to not block event loop
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        results = await loop.run_in_executor(executor, _sync_search)

    return results


async def search_arxiv_api(
    query: str,
    http_client: httpx.AsyncClient,
    max_results: int = 10,
) -> list[dict]:
    """
    Search arXiv API for papers.

    Args:
        query: Search query
        http_client: HTTP client
        max_results: Maximum number of results

    Returns:
        List of paper dictionaries
    """
    try:
        response = await http_client.get(
            ARXIV_API_URL,
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            timeout=30.0,
        )
        response.raise_for_status()

        # Parse XML response
        root = ElementTree.fromstring(response.text)

        # Define namespaces
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        papers = []
        for entry in root.findall("atom:entry", ns):
            # Extract paper info
            title_elem = entry.find("atom:title", ns)
            summary_elem = entry.find("atom:summary", ns)
            id_elem = entry.find("atom:id", ns)
            published_elem = entry.find("atom:published", ns)

            # Get authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns)
                if name is not None and name.text:
                    authors.append(name.text)

            # Get categories
            categories = []
            for category in entry.findall("atom:category", ns):
                term = category.get("term")
                if term:
                    categories.append(term)

            paper = {
                "title": title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else "Unknown",
                "authors": authors[:5],  # Limit to first 5 authors
                "abstract": summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else "",
                "arxiv_id": id_elem.text.split("/")[-1] if id_elem is not None and id_elem.text else "",
                "url": id_elem.text if id_elem is not None else "",
                "published": published_elem.text[:10] if published_elem is not None and published_elem.text else "",
                "categories": categories[:3],
            }
            papers.append(paper)

        return papers

    except Exception as e:
        logger.error(f"arXiv API error: {e}")
        raise


# =============================================================================
# Semantic Scholar API (legacy, for backward compatibility)
# =============================================================================

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


async def search_semantic_scholar_api(
    query: str,
    http_client: httpx.AsyncClient,
    max_results: int = 10,
) -> list[dict]:
    """
    Search Semantic Scholar API for papers.

    Args:
        query: Search query
        http_client: HTTP client
        max_results: Maximum number of results

    Returns:
        List of paper dictionaries
    """
    try:
        response = await http_client.get(
            SEMANTIC_SCHOLAR_API_URL,
            params={
                "query": query,
                "limit": max_results,
                "fields": "title,authors,abstract,year,citationCount,url,paperId",
            },
            timeout=30.0,
        )
        response.raise_for_status()

        data = response.json()
        papers = []

        for item in data.get("data", []):
            authors = [
                a.get("name", "Unknown")
                for a in item.get("authors", [])[:5]
            ]

            paper = {
                "title": item.get("title", "Unknown"),
                "authors": authors,
                "abstract": item.get("abstract", "")[:500] if item.get("abstract") else "",
                "year": item.get("year"),
                "citation_count": item.get("citationCount", 0),
                "url": item.get("url", ""),
                "paper_id": item.get("paperId", ""),
            }
            papers.append(paper)

        return papers

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("Semantic Scholar rate limit hit")
            return []
        raise
    except Exception as e:
        logger.error(f"Semantic Scholar API error: {e}")
        raise


# =============================================================================
# System Prompts
# =============================================================================

RESEARCH_SYSTEM_PROMPT_CHAT = """You are a specialized academic research assistant that helps users find relevant academic papers.

## Research Preferences (Already Collected via HITL)

The user has already provided their preferences through the preference modal:
- **Domain**: Check the context for the selected research domain
- **Venues**: Check the context for any venue restrictions

## YOUR WORKFLOW

### Step 1: Search Based on Preferences
Use the provided domain and venue preferences to search:
- `search_google_scholar` for broad academic coverage

**IMPORTANT: LIMIT YOUR SEARCHES**
- Make only 1-2 search queries total
- Use a well-crafted query that combines keywords (e.g., "vision language action models robotics 2024")
- Do NOT make many separate searches - Google Scholar will block excessive requests

Refine your search query using the domain context. For example:
- If domain is "Machine Learning" and query is "control theory", search for "machine learning control theory"

### Step 2: Synthesize and Summarize
Don't just list papers. Provide a **synthesis**:
- Group papers by theme or approach
- Explain key contributions and how they relate
- Highlight seminal vs recent work
- Note any research gaps or open problems

## OUTPUT FORMAT

**Summary**: Brief overview of the research landscape.

**Key Themes**:
1. **Theme Name**: Description and representative papers
2. **Theme Name**: Description and representative papers

**Recommended Papers**:
For each paper:
- **Title**
- Authors (Year)
- Why it's relevant to the query
- Link: URL

**Research Gaps**: What questions remain open?

## CRITICAL REQUIREMENTS
1. **LIMIT SEARCHES TO 1-2** - Excessive searches will be blocked
2. **USE PROVIDED PREFERENCES** - Domain and venue filters have already been collected
3. **SYNTHESIZE, DON'T JUST LIST** - Provide analysis and connections
4. **INCLUDE LINKS** - Every paper needs a "Link: URL" line from search results
5. **COPY EXACT URLS** - Use URLs returned by search tools, never make up URLs
"""

RESEARCH_SYSTEM_PROMPT_VIBE = """You are an autonomous research agent conducting deep literature exploration.

{state_context}

## MANDATORY FIRST SEARCH

Your FIRST search tool call MUST be `search_google_scholar`. This is not optional.
Only use search_arxiv or search_semantic_scholar AFTER trying search_google_scholar first.

## OUTPUT FORMAT

For each paper, include the URL on a separate line:

**Paper Title**
Authors: Author1, Author2 et al. (Year)
Link: https://url-from-search-results

CRITICAL: Every paper MUST have a "Link:" line with the URL from search results.

## Research Preferences (Already Set via Modal)

The user has already provided their domain and venue preferences via the preference modal.
- Domain: Check ctx.deps.domain for the selected research domain
- Venues: Check ctx.deps.venue_filter for any venue restrictions

## Your Mission

Autonomously explore the literature on the given topic, identify research gaps, and generate novel hypotheses.

## Workflow Phases

### Phase 1: SCOPING (Current if phase is scoping)
Clarify the research parameters:
- Domain focus (from user preferences)
- Specific constraints (efficiency, accuracy, scale, etc.)
- Desired output (survey, novel angle, idea validation)

**REQUIRED ACTION**: Call `define_scope` with the clarified parameters, then call `advance_phase` to move to DISCOVERY.

### Phase 2: DISCOVERY
Search comprehensively using ALL available tools:
1. Call `search_google_scholar` for broad academic coverage with citation counts
2. Call `search_pubmed` for biomedical and life sciences papers
3. Call `search_arxiv` with multiple query variations (at least 5-10 different queries)
4. Call `search_semantic_scholar` for citation-rich papers
5. Call `search_web` for papers from ACM, IEEE, OpenReview (fallback)
6. Call `search_top_cited` to find seminal/foundational papers (100+ citations)
7. Call `search_by_author` to find work by key researchers you discover
8. Call `search_venue` to find papers from top venues (NeurIPS, ICML, ICLR, ACL, CVPR, etc.)
9. Call `explore_citations` to follow seminal paper trails
10. Call `find_related_papers` to discover related work for key papers
11. Call `lookup_citation` to get full metadata for papers with DOI/PMID
12. Goal: Find 50-100+ relevant papers from diverse sources

**REQUIRED**: After each search, call `update_progress` to track findings.
When you have enough papers (50+), call `advance_phase` to move to SYNTHESIS.

### Phase 3: SYNTHESIS
**CRITICAL: You MUST read papers, not just abstracts!**

Read and analyze key papers thoroughly:
1. Call `read_arxiv_paper` for AT LEAST 15-20 papers (prioritize by citations)
2. For each paper you read, extract key findings before moving to the next
3. Call `record_theme` ONLY after reading multiple papers that share an approach
4. Themes should be based on deep understanding, not just titles/abstracts

**MINIMUM REQUIREMENT**: Do NOT advance to IDEATION until you have:
- Read at least 15 papers with `read_arxiv_paper`
- Recorded at least 5 themes with `record_theme`

Look for:
- Main methodological approaches
- Areas of agreement/disagreement
- Evolution of the field over time

When you meet the minimum requirements and themes are clear, call `advance_phase` to move to IDEATION.

### Phase 4: IDEATION
Find what's missing and propose new directions:
1. Call `record_gap` for each underexplored area found
2. Call `generate_hypothesis` to propose how to address each gap
3. Consider:
   - What combinations haven't been tried?
   - What domains lack application?
   - What assumptions could be challenged?

When you have enough hypotheses (3-5), call `advance_phase` to move to EVALUATION.

### Phase 5: EVALUATION
Score and rank your hypotheses:
1. Call `score_hypothesis` with novelty, feasibility, impact (1-10 each)
2. Identify similar existing work for each
3. Explain differentiation from prior work
4. Call `generate_report` to synthesize all findings

## Progress Rules

- ALWAYS call `update_progress` after each significant action
- If stalled (3 actions with no new info), change strategy or advance phase
- Use `advance_phase` when ready to move forward

## Critical Rules

1. NEVER fabricate citations - only cite papers from API results
2. Be thorough - explore widely before concluding
3. Be self-critical - identify weaknesses in your hypotheses
4. Every response should include at least one tool call
5. If unsure about scope, make reasonable assumptions and proceed
"""


# =============================================================================
# Research Agent
# =============================================================================

@register_subagent("research")
class ResearchAgent(Subagent[ResearchDeps]):
    """
    Research subagent for academic paper search and analysis.

    Supports two modes:
    - CHAT: Quick searches, paper summaries (cheaper model, faster)
    - VIBE: Deep autonomous research with hypothesis generation (stronger model, longer)

    Tools (CHAT mode):
        - search_arxiv: Search arXiv for papers
        - search_semantic_scholar: Search Semantic Scholar
        - search_web: Search web for papers from ACM, IEEE, PubMed, Google Scholar, etc.
        - read_arxiv_paper: Read full paper text
        - read_pdf_url: Read PDF from URL
        - think: Reasoning tool

    Additional tools (VIBE mode):
        - define_scope: Clarify research parameters
        - explore_citations: Follow citation trails
        - search_by_author: Find papers by specific researchers
        - find_related_papers: Get similar papers to a given paper
        - search_top_cited: Find highly-cited/influential papers
        - search_venue: Search papers from specific conferences/journals
        - record_theme: Track identified themes
        - record_gap: Document research gaps
        - generate_hypothesis: Propose novel ideas
        - score_hypothesis: Evaluate novelty/feasibility/impact
        - update_progress: Track progress with stall detection
        - advance_phase: Move through workflow
        - generate_report: Synthesize final report
        - save_to_memory: Persist findings
    """

    def __init__(self, mode: ResearchMode = ResearchMode.CHAT, provider_config: dict | None = None, **kwargs):
        self.mode = mode
        self._vibe_state_override: Optional["VibeResearchState"] = None
        self._provider_config = provider_config  # Store provider config for model creation

        # Configure based on mode
        if mode == ResearchMode.VIBE:
            config = SubagentConfig(
                name="research",
                description="Deep autonomous research with hypothesis generation",
                max_iterations=50,  # More iterations for vibe mode
                timeout=600.0,      # 10 minutes for deep research
                use_haiku=False,    # Use stronger model
            )
        else:
            config = SubagentConfig(
                name="research",
                description="Search and analyze academic papers from arXiv and Semantic Scholar",
                max_iterations=5,   # Limited iterations for focused search
                timeout=60.0,       # 1 minute should be enough for targeted search
                use_haiku=True,     # Cheaper model for quick queries
            )

        super().__init__(config)
        self._http_client: httpx.AsyncClient | None = None
        self._s2_client: SemanticScholarClient | None = None

    def _get_model(self):
        """Get the appropriate model for this subagent.

        Uses provider_config if provided, otherwise falls back to default haiku model.
        """
        from agent.providers import get_model

        if self._provider_config:
            # Use provider config from frontend settings
            return get_model(
                provider=self._provider_config.get("name", "openrouter"),
                model_id=self._provider_config.get("model"),
                api_key=self._provider_config.get("api_key"),
            )

        # Fallback to default haiku model
        return get_haiku_model()

    async def run(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        *,
        project_path: str | None = None,
        mode: ResearchMode | None = None,
        vibe_state: Optional["VibeResearchState"] = None,
    ) -> "SubagentResult":
        """
        Run the research agent on a task.

        This override handles vibe-mode specific parameters and appends
        collected paper links to the final output.

        Args:
            task: The task to perform
            context: Optional context dictionary
            project_path: Path to the project (for vibe mode)
            mode: Override the mode (CHAT or VIBE)
            vibe_state: VibeResearchState for vibe mode

        Returns:
            SubagentResult with output and metadata
        """
        import asyncio
        import re
        from datetime import datetime, timezone

        # Build context from kwargs
        ctx = context or {}

        if project_path is not None:
            ctx["project_path"] = project_path

        if mode is not None:
            ctx["mode"] = "vibe" if mode == ResearchMode.VIBE else "chat"
            # If mode changed, invalidate cached agent so it gets recreated with correct tools
            if mode != self.mode:
                self._agent = None
            self.mode = mode

        if vibe_state is not None:
            self._vibe_state_override = vibe_state
            ctx["session_id"] = vibe_state.session_id

        started_at = datetime.now(timezone.utc)
        logger.info(f"Subagent '{self.config.name}' starting task: {task[:100]}...")

        # Both CHAT and VIBE modes use the agent with tools
        max_retries = 3
        retry_delay = 5.0

        for attempt in range(max_retries + 1):
            try:
                async with asyncio.timeout(self.config.timeout):
                    deps = self._create_deps(ctx)
                    result = await self.agent.run(task, deps=deps)

                completed_at = datetime.now(timezone.utc)
                duration = (completed_at - started_at).total_seconds()
                usage = result.usage()

                logger.info(
                    f"Subagent '{self.config.name}' completed in {duration:.1f}s "
                    f"({usage.input_tokens}in/{usage.output_tokens}out tokens)"
                )

                # Get the model's output
                output = result.output or ""

                # Append collected paper links
                if deps.collected_papers:
                    seen_urls = set()
                    unique_papers = []
                    for paper in deps.collected_papers:
                        if paper.url not in seen_urls:
                            seen_urls.add(paper.url)
                            unique_papers.append(paper)

                    if unique_papers:
                        output += "\n\n---\n**Sources:**\n"
                        for paper in unique_papers:
                            year_str = f" ({paper.year})" if paper.year else ""
                            output += f"- [{paper.title}]({paper.url}){year_str}\n"

                return SubagentResult(
                    output=output,
                    subagent_name=self.config.name,
                    task=task,
                    success=True,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=duration,
                    input_tokens=usage.input_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0,
                )

            except asyncio.TimeoutError:
                logger.error(f"Subagent '{self.config.name}' timed out after {self.config.timeout}s")
                return SubagentResult(
                    output=f"Error: Task timed out after {self.config.timeout} seconds",
                    subagent_name=self.config.name,
                    task=task,
                    success=False,
                    error="timeout",
                    started_at=started_at,
                )

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries:
                        logger.warning(
                            f"Subagent '{self.config.name}' hit rate limit, "
                            f"retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue

                logger.error(f"Subagent '{self.config.name}' failed: {e}")
                return SubagentResult(
                    output=f"Error: {str(e)}",
                    subagent_name=self.config.name,
                    task=task,
                    success=False,
                    error=str(e),
                    started_at=started_at,
                )

        return SubagentResult(
            output="Error: Max retries exceeded",
            subagent_name=self.config.name,
            task=task,
            success=False,
            error="max_retries",
            started_at=started_at,
        )

    def _extract_search_query(self, task: str) -> str:
        """Extract a search query from the task description."""
        import re

        # Remove common prefixes
        task = re.sub(r'^(Search for|Find|Look for|Get)\s+(academic\s+)?(papers?|articles?)\s+(about|on|regarding|related to)\s+', '', task, flags=re.IGNORECASE)

        # Take first sentence or first 100 chars
        task = task.split('.')[0].strip()
        if len(task) > 100:
            task = task[:100]

        # Remove venue filter requests
        task = re.sub(r'\s*\(.*venue.*\).*', '', task, flags=re.IGNORECASE)

        return task.strip() or "academic papers"

    @property
    def system_prompt(self) -> str:
        if self.mode == ResearchMode.VIBE:
            return RESEARCH_SYSTEM_PROMPT_VIBE
        return RESEARCH_SYSTEM_PROMPT_CHAT

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=5.0),
                follow_redirects=True,
            )
        return self._http_client

    def _get_s2_client(self) -> SemanticScholarClient:
        """Get or create Semantic Scholar client."""
        if self._s2_client is None:
            self._s2_client = SemanticScholarClient(self._get_http_client())
        return self._s2_client

    def _create_deps(self, context: dict[str, Any]) -> ResearchDeps:
        """Create dependencies for research agent."""
        mode_str = context.get("mode", "chat")
        mode = ResearchMode.VIBE if mode_str == "vibe" else ResearchMode.CHAT

        # For vibe mode, create or load state
        vibe_state = None
        if mode == ResearchMode.VIBE:
            # First check for override (passed directly via run())
            if self._vibe_state_override is not None:
                vibe_state = self._vibe_state_override
            else:
                # Try to load from file
                project_path = context.get("project_path", "")
                session_id = context.get("session_id")

                if session_id and project_path:
                    vibe_state = VibeResearchState.load(project_path, session_id)

                if vibe_state is None:
                    vibe_state = VibeResearchState(topic=context.get("topic", ""))

        # Get research preferences from context (passed by delegate_to_subagent)
        domain = context.get("domain", "")
        venue_filter = context.get("venue_filter", [])
        venue_preferences_asked = context.get("venue_preferences_asked", False)

        return ResearchDeps(
            http_client=self._get_http_client(),
            max_results=context.get("max_results", 10),
            mode=mode,
            project_path=context.get("project_path", ""),
            vibe_state=vibe_state,
            domain=domain,
            venue_filter=venue_filter,
            venue_preferences_asked=venue_preferences_asked,
        )

    def _create_agent(self) -> Agent[ResearchDeps, str]:
        """Create the research agent with tools."""

        # Create agent with appropriate base prompt
        if self.mode == ResearchMode.VIBE:
            # For vibe mode, use the base vibe prompt (state will be injected dynamically)
            agent = Agent(
                model=self._get_model(),
                system_prompt=RESEARCH_SYSTEM_PROMPT_VIBE.format(state_context=""),
                deps_type=ResearchDeps,
                retries=2,
            )

            # Add dynamic system prompt that injects current state
            @agent.system_prompt
            def inject_vibe_state(ctx: RunContext[ResearchDeps]) -> str:
                """Inject current vibe state into the context."""
                if ctx.deps.vibe_state:
                    return f"\n## Current Research State\n{ctx.deps.vibe_state.to_context()}"
                return ""
        else:
            agent = Agent(
                model=self._get_model(),
                system_prompt=RESEARCH_SYSTEM_PROMPT_CHAT,
                deps_type=ResearchDeps,
                retries=2,
            )

            # Add dynamic system prompt that injects research preferences
            @agent.system_prompt
            def inject_research_preferences(ctx: RunContext[ResearchDeps]) -> str:
                """Inject research preferences (domain, venues) into the context."""
                parts = []
                if ctx.deps.domain:
                    parts.append(f"**Selected Domain**: {ctx.deps.domain}")
                if ctx.deps.venue_filter:
                    venues_str = ", ".join(ctx.deps.venue_filter)
                    parts.append(f"**Selected Venues**: {venues_str}")
                if parts:
                    return "\n## User's Research Preferences\n" + "\n".join(parts) + "\n\nUse these preferences to refine your search and prioritize relevant papers."
                return ""

        # === CHAT TOOLS (Google Scholar ONLY - for quick searches) ===
        if self.mode == ResearchMode.CHAT:
            self._register_chat_tools(agent)
            logger.info(f"CHAT mode: registered tools = {list(agent._function_toolset.tools.keys())}")
        else:
            # === ALL TOOLS (VIBE mode - comprehensive research) ===
            self._register_core_tools(agent)
            self._register_vibe_tools(agent)
            logger.info(f"VIBE mode: registered tools = {list(agent._function_toolset.tools.keys())}")

        return agent

    def _register_chat_tools(self, agent: Agent):
        """Register minimal tools for CHAT mode (Google Scholar ONLY)."""

        @agent.tool
        async def search_google_scholar(
            ctx: RunContext[ResearchDeps],
            query: str,
            max_results: int = 10,
            year_start: int | None = None,
            year_end: int | None = None,
        ) -> str:
            """
            Search Google Scholar for academic papers.

            Args:
                query: Search query (e.g., "deep learning medical imaging")
                max_results: Maximum results (1-20)
                year_start: Filter papers from this year
                year_end: Filter papers until this year

            Returns:
                List of papers with titles, authors, and clickable links
            """
            max_results = min(max(1, max_results), 20)

            try:
                client = GoogleScholarClient(ctx.deps.http_client)
                results = await client.search(
                    query=query,
                    max_results=max_results,
                    year_start=year_start,
                    year_end=year_end,
                )

                if not results:
                    return f"No papers found on Google Scholar for query: '{query}'"

                # Collect papers with links for Sources section
                for paper in results:
                    if paper.url:
                        authors_str = ", ".join(paper.authors[:3]) if paper.authors else ""
                        if len(paper.authors) > 3:
                            authors_str += " et al."
                        ctx.deps.collected_papers.append(CollectedPaper(
                            title=paper.title,
                            url=paper.url,
                            authors=authors_str,
                            year=paper.year,
                        ))

                return format_results(results, query, "Google Scholar")

            except Exception as e:
                error_msg = str(e)
                # If CAPTCHA or rate limited, try Semantic Scholar as fallback
                if "CAPTCHA" in error_msg or "rate" in error_msg.lower():
                    logger.warning(f"Google Scholar blocked, falling back to Semantic Scholar: {error_msg}")
                    try:
                        s2_client = SemanticScholarClient(ctx.deps.http_client)
                        s2_results = await s2_client.search(query=query, limit=max_results)

                        if not s2_results:
                            return f"Google Scholar is blocked (CAPTCHA). Semantic Scholar also found no results for: '{query}'"

                        # Collect papers with links
                        for paper in s2_results:
                            if paper.get("url"):
                                authors = paper.get("authors", [])
                                authors_str = ", ".join(a.get("name", "") for a in authors[:3])
                                if len(authors) > 3:
                                    authors_str += " et al."
                                ctx.deps.collected_papers.append(CollectedPaper(
                                    title=paper.get("title", ""),
                                    url=paper.get("url", ""),
                                    authors=authors_str,
                                    year=paper.get("year"),
                                ))

                        # Format S2 results
                        lines = [f"(Google Scholar blocked - using Semantic Scholar) Found {len(s2_results)} papers for '{query}':\n"]
                        for i, paper in enumerate(s2_results, 1):
                            title = paper.get("title", "Unknown")
                            authors = paper.get("authors", [])
                            authors_str = ", ".join(a.get("name", "") for a in authors[:3])
                            if len(authors) > 3:
                                authors_str += " et al."
                            year = paper.get("year", "")
                            url = paper.get("url", "")
                            citations = paper.get("citationCount", 0)

                            lines.append(f"{i}. **{title}**")
                            if authors_str:
                                lines.append(f"   Authors: {authors_str}")
                            if year:
                                lines.append(f"   Year: {year}")
                            if citations:
                                lines.append(f"   Citations: {citations}")
                            if url:
                                lines.append(f"   Link: {url}")
                            lines.append("")

                        return "\n".join(lines)

                    except Exception as s2_error:
                        return f"Google Scholar blocked (CAPTCHA) and Semantic Scholar also failed: {s2_error}"

                return f"Error searching Google Scholar: {error_msg}"

    def _register_core_tools(self, agent: Agent):
        """Register core research tools (existing tools)."""

        @agent.tool
        async def get_research_preferences(
            ctx: RunContext[ResearchDeps],
        ) -> str:
            """
            Get the current research preferences (domain and venue filter).

            Preferences are set by the user via a modal before research begins.

            Returns:
                Current domain and venue preferences
            """
            domain = ctx.deps.domain or "Not specified"
            venues = ctx.deps.venue_filter

            if venues:
                venues_str = ", ".join(venues)
                return f"""Research Preferences:
- Domain: {domain}
- Venue filter: {venues_str}

Searches will prioritize papers from these venues."""
            else:
                return f"""Research Preferences:
- Domain: {domain}
- Venue filter: None (searching all venues)

Proceed with broad search across all venues."""

        def _apply_venue_filter(query: str, venue_filter: list[str]) -> str:
            """Helper to enhance query with venue filter."""
            if not venue_filter:
                return query
            # Add venue names to query for better results
            venues_str = " OR ".join(venue_filter)
            return f"{query} ({venues_str})"

        @agent.tool
        async def search_arxiv(
            ctx: RunContext[ResearchDeps],
            query: str,
            max_results: int = 5,
        ) -> str:
            """
            Search arXiv for preprints. NOTE: Use search_google_scholar first for better coverage.

            Only use this if search_google_scholar doesn't find enough results.

            Args:
                query: Search query (e.g., "transformer attention mechanisms")
                max_results: Maximum number of results (1-10)

            Returns:
                List of papers with titles, authors, abstracts, and links
            """
            max_results = min(max(1, max_results), 10)

            # Apply venue filter if set
            enhanced_query = _apply_venue_filter(query, ctx.deps.venue_filter)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching arXiv for '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                papers = await search_arxiv_api(
                    query=enhanced_query,
                    http_client=ctx.deps.http_client,
                    max_results=max_results,
                )

                if not papers:
                    return f"No papers found on arXiv for query: '{query}'"

                # In vibe mode, add to state and save
                if ctx.deps.mode == ResearchMode.VIBE and ctx.deps.vibe_state:
                    for paper in papers:
                        ctx.deps.vibe_state.add_paper({
                            "paper_id": paper["arxiv_id"],
                            "title": paper["title"],
                            "authors": paper["authors"],
                            "year": int(paper["published"][:4]) if paper["published"] else None,
                            "citation_count": 0,
                            "abstract": paper["abstract"],
                        }, source="arxiv")
                    # Save state so UI can show progress
                    if ctx.deps.project_path:
                        ctx.deps.vibe_state.save(ctx.deps.project_path)

                # Format results
                lines = [f"Found {len(papers)} papers on arXiv for '{query}':\n"]
                for i, paper in enumerate(papers, 1):
                    authors_str = ", ".join(paper["authors"][:3])
                    if len(paper["authors"]) > 3:
                        authors_str += " et al."

                    arxiv_url = f"https://arxiv.org/abs/{paper['arxiv_id']}"
                    lines.append(f"{i}. **[{paper['title']}]({arxiv_url})**")
                    lines.append(f"   Authors: {authors_str}")
                    lines.append(f"   Published: {paper['published']}")
                    lines.append(f"   Link: {arxiv_url}")

                    abstract = paper["abstract"][:300]
                    if len(paper["abstract"]) > 300:
                        abstract += "..."
                    lines.append(f"   Abstract: {abstract}")
                    lines.append("")

                return "\n".join(lines)

            except Exception as e:
                return f"Error searching arXiv: {str(e)}"

        @agent.tool
        async def search_semantic_scholar(
            ctx: RunContext[ResearchDeps],
            query: str,
            max_results: int = 5,
        ) -> str:
            """
            Search Semantic Scholar for citation networks. Use search_google_scholar first.

            Good for exploring citation relationships after initial search.

            Args:
                query: Search query
                max_results: Maximum number of results (1-10)

            Returns:
                List of papers with citation counts and links
            """
            max_results = min(max(1, max_results), 10)

            # Apply venue filter if set
            enhanced_query = _apply_venue_filter(query, ctx.deps.venue_filter)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching Semantic Scholar for '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                papers = await search_semantic_scholar_api(
                    query=enhanced_query,
                    http_client=ctx.deps.http_client,
                    max_results=max_results,
                )

                if not papers:
                    return f"No papers found on Semantic Scholar for query: '{query}'"

                # In vibe mode, add to state and save
                if ctx.deps.mode == ResearchMode.VIBE and ctx.deps.vibe_state:
                    for paper in papers:
                        ctx.deps.vibe_state.add_paper({
                            "paper_id": paper["paper_id"],
                            "title": paper["title"],
                            "authors": paper["authors"],
                            "year": paper["year"],
                            "citation_count": paper["citation_count"],
                            "abstract": paper["abstract"],
                        }, source="semantic_scholar")
                    # Save state so UI can show progress
                    if ctx.deps.project_path:
                        ctx.deps.vibe_state.save(ctx.deps.project_path)

                # Format results
                lines = [f"Found {len(papers)} papers on Semantic Scholar for '{query}':\n"]
                for i, paper in enumerate(papers, 1):
                    authors_str = ", ".join(paper["authors"][:3])
                    if len(paper["authors"]) > 3:
                        authors_str += " et al."

                    year_str = f" ({paper['year']})" if paper["year"] else ""
                    s2_url = f"https://www.semanticscholar.org/paper/{paper['paper_id']}"

                    lines.append(f"{i}. **[{paper['title']}]({s2_url})**{year_str}")
                    lines.append(f"   Authors: {authors_str}")
                    lines.append(f"   Citations: {paper['citation_count']}")
                    lines.append(f"   Link: {s2_url}")

                    if paper["abstract"]:
                        abstract = paper["abstract"][:300]
                        if len(paper["abstract"]) > 300:
                            abstract += "..."
                        lines.append(f"   Abstract: {abstract}")
                    lines.append("")

                return "\n".join(lines)

            except Exception as e:
                return f"Error searching Semantic Scholar: {str(e)}"

        @agent.tool
        async def search_web(
            ctx: RunContext[ResearchDeps],
            query: str,
            max_results: int = 10,
        ) -> str:
            """
            Search the web for academic papers from multiple sources.

            Use this to find papers from Google Scholar, ACM, IEEE, PubMed,
            OpenReview, and other sources beyond arXiv and Semantic Scholar.

            Best for:
            - Finding papers from specific venues (ACM, IEEE conferences)
            - Searching medical/biology papers (PubMed)
            - Discovering workshop papers and preprints
            - Broader coverage when arXiv/S2 results are insufficient

            Args:
                query: Search query (e.g., "attention mechanism transformers")
                max_results: Maximum number of results (1-15)

            Returns:
                List of papers with titles, sources, and snippets
            """
            max_results = min(max(1, max_results), 15)

            # Apply venue filter if set
            enhanced_query = _apply_venue_filter(query, ctx.deps.venue_filter)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching web for '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                papers = await search_web_for_papers(
                    query=enhanced_query,
                    http_client=ctx.deps.http_client,
                    max_results=max_results,
                )

                if not papers:
                    return f"No papers found on the web for query: '{query}'"

                # In vibe mode, add to state and save
                if ctx.deps.mode == ResearchMode.VIBE and ctx.deps.vibe_state:
                    for paper in papers:
                        ctx.deps.vibe_state.add_paper({
                            "paper_id": paper["url"],  # Use URL as ID
                            "title": paper["title"],
                            "authors": [],
                            "year": None,
                            "citation_count": 0,
                            "abstract": paper["snippet"],
                        }, source=f"web:{paper['source']}")
                    # Save state so UI can show progress
                    if ctx.deps.project_path:
                        ctx.deps.vibe_state.save(ctx.deps.project_path)

                # Format results
                lines = [f"Found {len(papers)} papers from web search for '{query}':\n"]
                for i, paper in enumerate(papers, 1):
                    source_label = paper["source"].upper().replace("_", " ")
                    url = paper['url']

                    lines.append(f"{i}. **[{paper['title']}]({url})**")
                    lines.append(f"   Source: {source_label}")
                    lines.append(f"   Link: {url}")

                    if paper["snippet"]:
                        snippet = paper["snippet"][:300]
                        if len(paper["snippet"]) > 300:
                            snippet += "..."
                        lines.append(f"   Snippet: {snippet}")
                    lines.append("")

                return "\n".join(lines)

            except Exception as e:
                return f"Error searching the web: {str(e)}"

        @agent.tool
        async def think(ctx: RunContext[ResearchDeps], thought: str) -> str:
            """
            Think through a research question step-by-step.

            Use this to reason about:
            - Which search terms to use
            - How to combine results
            - How to synthesize findings
            - What gaps might exist

            Args:
                thought: Your reasoning process

            Returns:
                Acknowledgment to continue
            """
            return "Thinking recorded. Continue with your research."

        @agent.tool
        async def read_arxiv_paper(
            ctx: RunContext[ResearchDeps],
            arxiv_id: str,
            max_pages: int = 10,
        ) -> str:
            """
            Download and read the full text of an arXiv paper.

            Args:
                arxiv_id: arXiv paper ID (e.g., "2301.07041")
                max_pages: Maximum pages to extract (default: 10)

            Returns:
                Extracted text from the paper
            """
            from agent.tools.pdf_reader import read_arxiv_paper as _read_arxiv

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Reading paper {arxiv_id}...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                doc = await _read_arxiv(
                    arxiv_id=arxiv_id,
                    http_client=ctx.deps.http_client,
                    max_pages=max_pages,
                    max_chars=50000,
                )

                # In vibe mode, mark as read and save
                if ctx.deps.mode == ResearchMode.VIBE and ctx.deps.vibe_state:
                    if arxiv_id not in ctx.deps.vibe_state.papers_read:
                        ctx.deps.vibe_state.papers_read.append(arxiv_id)
                    # Save state so UI can show progress
                    if ctx.deps.project_path:
                        ctx.deps.vibe_state.save(ctx.deps.project_path)

                text = doc.get_text(max_pages=max_pages, max_chars=50000)
                return f"Paper: {doc.title}\nPages: {doc.num_pages}\narXiv: {arxiv_id}\n\n{text}"

            except FileNotFoundError:
                return f"Error: arXiv paper not found: {arxiv_id}"
            except Exception as e:
                return f"Error reading arXiv paper: {str(e)}"

        @agent.tool
        async def read_pdf_url(
            ctx: RunContext[ResearchDeps],
            url: str,
            max_pages: int = 10,
        ) -> str:
            """
            Download and read a PDF from any URL.

            Args:
                url: Direct URL to a PDF file
                max_pages: Maximum pages to extract (default: 10)

            Returns:
                Extracted text from the PDF
            """
            from agent.tools.pdf_reader import read_pdf_from_url as _read_pdf

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Reading PDF from URL...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                doc = await _read_pdf(
                    url=url,
                    http_client=ctx.deps.http_client,
                    max_pages=max_pages,
                )

                text = doc.get_text(max_pages=max_pages, max_chars=50000)
                return f"Paper: {doc.title}\nPages: {doc.num_pages}\nURL: {url}\n\n{text}"

            except Exception as e:
                return f"Error reading PDF from URL: {str(e)}"

        # =====================================================================
        # Citation Management Tools (from skillsbench)
        # =====================================================================

        @agent.tool
        async def search_google_scholar(
            ctx: RunContext[ResearchDeps],
            query: str,
            max_results: int = 10,
            year_start: int | None = None,
            year_end: int | None = None,
        ) -> str:
            """
            PRIMARY SEARCH TOOL - Search Google Scholar for academic papers.

            USE THIS TOOL FIRST for any academic paper search. It has the best coverage
            across all disciplines and includes citation counts.

            Args:
                query: Search query (e.g., "deep learning medical imaging")
                max_results: Maximum results (1-20)
                year_start: Filter papers from this year
                year_end: Filter papers until this year

            Returns:
                List of papers with titles, authors, citations, and clickable links
            """
            max_results = min(max(1, max_results), 20)

            # Apply venue filter if set
            enhanced_query = _apply_venue_filter(query, ctx.deps.venue_filter)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching Google Scholar for '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                client = GoogleScholarClient(ctx.deps.http_client)
                results = await client.search(
                    query=enhanced_query,
                    max_results=max_results,
                    year_start=year_start,
                    year_end=year_end,
                )

                if not results:
                    return f"No papers found on Google Scholar for query: '{query}'"

                # Collect papers with links for post-processing
                for paper in results:
                    if paper.url:
                        authors_str = ", ".join(paper.authors[:3]) if paper.authors else ""
                        if len(paper.authors) > 3:
                            authors_str += " et al."
                        ctx.deps.collected_papers.append(CollectedPaper(
                            title=paper.title,
                            url=paper.url,
                            authors=authors_str,
                            year=paper.year,
                        ))

                # In vibe mode, add to state
                if ctx.deps.mode == ResearchMode.VIBE and ctx.deps.vibe_state:
                    for paper in results:
                        ctx.deps.vibe_state.add_paper({
                            "paper_id": paper.url or paper.title,
                            "title": paper.title,
                            "authors": paper.authors,
                            "year": paper.year,
                            "citation_count": paper.citation_count,
                            "abstract": paper.abstract or "",
                        }, source="google_scholar")
                    if ctx.deps.project_path:
                        ctx.deps.vibe_state.save(ctx.deps.project_path)

                return format_results(results, query, "Google Scholar")

            except ImportError:
                return "Error: scholarly library not installed. Install with: pip install scholarly"
            except Exception as e:
                return f"Error searching Google Scholar: {str(e)}"

        @agent.tool
        async def search_pubmed(
            ctx: RunContext[ResearchDeps],
            query: str,
            max_results: int = 10,
            year_start: int | None = None,
            year_end: int | None = None,
        ) -> str:
            """
            Search PubMed for biomedical and life sciences papers.

            Essential for medical, biological, and health-related research.

            Args:
                query: Search query (e.g., "CRISPR cancer therapy")
                max_results: Maximum results (1-50)
                year_start: Filter papers from this year
                year_end: Filter papers until this year

            Returns:
                List of papers with titles, authors, journals, and links
            """
            max_results = min(max(1, max_results), 50)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching PubMed for '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                client = PubMedClient(ctx.deps.http_client)
                results = await client.search(
                    query=query,
                    max_results=max_results,
                    year_start=year_start,
                    year_end=year_end,
                )

                if not results:
                    return f"No papers found on PubMed for query: '{query}'"

                # Collect papers with links for post-processing
                for paper in results:
                    if paper.url:
                        authors_str = ", ".join(paper.authors[:3]) if paper.authors else ""
                        if len(paper.authors) > 3:
                            authors_str += " et al."
                        ctx.deps.collected_papers.append(CollectedPaper(
                            title=paper.title,
                            url=paper.url,
                            authors=authors_str,
                            year=paper.year,
                        ))

                # In vibe mode, add to state
                if ctx.deps.mode == ResearchMode.VIBE and ctx.deps.vibe_state:
                    for paper in results:
                        ctx.deps.vibe_state.add_paper({
                            "paper_id": paper.pmid or paper.doi or paper.title,
                            "title": paper.title,
                            "authors": paper.authors,
                            "year": paper.year,
                            "citation_count": 0,
                            "abstract": paper.abstract or "",
                        }, source="pubmed")
                    if ctx.deps.project_path:
                        ctx.deps.vibe_state.save(ctx.deps.project_path)

                return format_results(results, query, "PubMed")

            except Exception as e:
                return f"Error searching PubMed: {str(e)}"

        @agent.tool
        async def lookup_citation(
            ctx: RunContext[ResearchDeps],
            identifier: str,
        ) -> str:
            """
            Look up citation metadata from a DOI, PMID, or URL.

            Extracts full metadata for generating BibTeX entries.

            Args:
                identifier: DOI (10.xxxx/...), PMID (8+ digits), or paper URL

            Returns:
                Citation metadata including title, authors, year, venue
            """
            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Looking up citation: {identifier[:50]}...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            try:
                extractor = MetadataExtractor(ctx.deps.http_client)
                id_type, cleaned_id = extractor.identify_type(identifier)

                if id_type == "unknown":
                    return f"Could not identify identifier type: {identifier}"

                result = await extractor.extract(identifier)

                if not result:
                    return f"Could not find metadata for {id_type}: {cleaned_id}"

                # Format result
                lines = [f"**{result.title}**\n"]
                lines.append(f"- Authors: {', '.join(result.authors[:5])}")
                if len(result.authors) > 5:
                    lines[-1] += " et al."
                if result.year:
                    lines.append(f"- Year: {result.year}")
                if result.venue:
                    lines.append(f"- Venue: {result.venue}")
                if result.doi:
                    lines.append(f"- DOI: {result.doi}")
                if result.pmid:
                    lines.append(f"- PMID: {result.pmid}")
                if result.url:
                    lines.append(f"- URL: {result.url}")
                if result.abstract:
                    abstract = result.abstract[:500]
                    if len(result.abstract) > 500:
                        abstract += "..."
                    lines.append(f"\nAbstract: {abstract}")

                return "\n".join(lines)

            except Exception as e:
                return f"Error looking up citation: {str(e)}"

    def _register_vibe_tools(self, agent: Agent):
        """Register tools specific to vibe research workflow."""

        @agent.tool
        async def define_scope(
            ctx: RunContext[ResearchDeps],
            domain: str,
            constraints: str,
            goal: str,
            additional_notes: str = "",
        ) -> str:
            """
            Define the scope of the research.

            Call this in the SCOPING phase to clarify parameters.

            Args:
                domain: Primary domain (e.g., "NLP", "computer vision", "multimodal")
                constraints: Key constraints (e.g., "efficiency", "low-resource")
                goal: Research goal (e.g., "find novel angle", "literature survey")
                additional_notes: Any other relevant scope info

            Returns:
                Confirmation to proceed
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available. Are you in VIBE mode?"

            # Set activity
            ctx.deps.vibe_state.set_activity("Defining research scope...")

            ctx.deps.vibe_state.scope = {
                "domain": domain,
                "constraints": constraints,
                "goal": goal,
                "notes": additional_notes,
            }

            # Save state
            if ctx.deps.project_path:
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            return f"Scope defined:\n- Domain: {domain}\n- Constraints: {constraints}\n- Goal: {goal}\n\nProceed to DISCOVERY phase with `advance_phase`."

        @agent.tool
        async def explore_citations(
            ctx: RunContext[ResearchDeps],
            paper_id: str,
            direction: str = "both",
            max_results: int = 20,
        ) -> str:
            """
            Explore the citation graph around a paper.

            Use this to find:
            - Papers that cite this one (follow-up work)
            - Papers this one cites (foundational work)

            Args:
                paper_id: Semantic Scholar paper ID (from search results)
                direction: "citations", "references", or "both"
                max_results: Maximum papers to return

            Returns:
                Connected papers with titles and citation counts
            """
            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Exploring citations for paper {paper_id}...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            s2_client = SemanticScholarClient(ctx.deps.http_client)

            try:
                papers = await s2_client.explore_citation_graph(
                    paper_id=paper_id,
                    direction=direction,  # type: ignore
                    depth=1,
                    max_papers_per_level=max_results,
                )
            except Exception as e:
                return f"Error exploring citations: {str(e)}"

            if not papers:
                return f"No connected papers found for {paper_id}"

            # Add to state if in vibe mode and save
            if ctx.deps.vibe_state:
                for paper in papers:
                    ctx.deps.vibe_state.add_paper(paper.to_dict(), source="citation_graph")
                # Save state so UI can show progress
                if ctx.deps.project_path:
                    ctx.deps.vibe_state.save(ctx.deps.project_path)

            # Format results
            lines = [f"Found {len(papers)} connected papers:\n"]
            for i, paper in enumerate(papers[:max_results], 1):
                year_str = f" ({paper.year})" if paper.year else ""
                lines.append(f"{i}. **{paper.title}**{year_str}")
                lines.append(f"   Citations: {paper.citation_count}")
                lines.append(f"   S2 ID: {paper.paper_id}")
                lines.append("")

            return "\n".join(lines)

        @agent.tool
        async def search_by_author(
            ctx: RunContext[ResearchDeps],
            author_name: str,
            max_results: int = 15,
        ) -> str:
            """
            Search for papers by a specific author/researcher.

            Use this when you want to find work by a key researcher in the field.

            Args:
                author_name: Name of the author (e.g., "Yoshua Bengio", "Geoffrey Hinton")
                max_results: Maximum papers to return (1-20)

            Returns:
                List of papers by this author
            """
            max_results = min(max(1, max_results), 20)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching papers by {author_name}...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            s2_client = SemanticScholarClient(ctx.deps.http_client)

            try:
                papers = await s2_client.search_by_author(author_name, limit=max_results)
            except Exception as e:
                return f"Error searching by author: {str(e)}"

            if not papers:
                return f"No papers found for author: {author_name}"

            # Add to state if in vibe mode and save
            if ctx.deps.vibe_state:
                for paper in papers:
                    ctx.deps.vibe_state.add_paper(paper.to_dict(), source="author_search")
                if ctx.deps.project_path:
                    ctx.deps.vibe_state.save(ctx.deps.project_path)

            # Format results
            lines = [f"Found {len(papers)} papers by {author_name}:\n"]
            for i, paper in enumerate(papers, 1):
                year_str = f" ({paper.year})" if paper.year else ""
                lines.append(f"{i}. **{paper.title}**{year_str}")
                lines.append(f"   Citations: {paper.citation_count}")
                lines.append(f"   S2 ID: {paper.paper_id}")
                lines.append("")

            return "\n".join(lines)

        @agent.tool
        async def find_related_papers(
            ctx: RunContext[ResearchDeps],
            paper_id: str,
            max_results: int = 10,
        ) -> str:
            """
            Find papers similar/related to a given paper.

            Use this to discover related work that might not show up in keyword search.

            Args:
                paper_id: Semantic Scholar paper ID to find related papers for
                max_results: Maximum papers to return (1-15)

            Returns:
                List of related/similar papers
            """
            max_results = min(max(1, max_results), 15)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Finding papers related to {paper_id}...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            s2_client = SemanticScholarClient(ctx.deps.http_client)

            try:
                papers = await s2_client.get_recommendations(paper_id, limit=max_results)
            except Exception as e:
                return f"Error finding related papers: {str(e)}"

            if not papers:
                return f"No related papers found for: {paper_id}"

            # Add to state if in vibe mode and save
            if ctx.deps.vibe_state:
                for paper in papers:
                    ctx.deps.vibe_state.add_paper(paper.to_dict(), source="recommendations")
                if ctx.deps.project_path:
                    ctx.deps.vibe_state.save(ctx.deps.project_path)

            # Format results
            lines = [f"Found {len(papers)} related papers:\n"]
            for i, paper in enumerate(papers, 1):
                year_str = f" ({paper.year})" if paper.year else ""
                lines.append(f"{i}. **{paper.title}**{year_str}")
                lines.append(f"   Citations: {paper.citation_count}")
                lines.append(f"   S2 ID: {paper.paper_id}")
                if paper.abstract:
                    abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                    lines.append(f"   Abstract: {abstract}")
                lines.append("")

            return "\n".join(lines)

        @agent.tool
        async def search_top_cited(
            ctx: RunContext[ResearchDeps],
            query: str,
            min_citations: int = 100,
            max_results: int = 15,
        ) -> str:
            """
            Find the most influential/highly-cited papers on a topic.

            Use this to identify seminal work and key papers in a field.

            Args:
                query: Topic to search for
                min_citations: Minimum citation count (default: 100)
                max_results: Maximum papers to return (1-20)

            Returns:
                Highly-cited papers sorted by citation count
            """
            max_results = min(max(1, max_results), 20)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Finding top-cited papers on '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            s2_client = SemanticScholarClient(ctx.deps.http_client)

            try:
                papers = await s2_client.search_top_cited(
                    query, limit=max_results, min_citations=min_citations
                )
            except Exception as e:
                return f"Error finding top-cited papers: {str(e)}"

            if not papers:
                return f"No papers found with {min_citations}+ citations for: {query}. Try lowering min_citations."

            # Add to state if in vibe mode and save
            if ctx.deps.vibe_state:
                for paper in papers:
                    ctx.deps.vibe_state.add_paper(paper.to_dict(), source="top_cited")
                if ctx.deps.project_path:
                    ctx.deps.vibe_state.save(ctx.deps.project_path)

            # Format results
            lines = [f"Found {len(papers)} highly-cited papers on '{query}':\n"]
            for i, paper in enumerate(papers, 1):
                year_str = f" ({paper.year})" if paper.year else ""
                lines.append(f"{i}. **{paper.title}**{year_str}")
                lines.append(f"   Citations: {paper.citation_count}")
                lines.append(f"   S2 ID: {paper.paper_id}")
                lines.append("")

            return "\n".join(lines)

        @agent.tool
        async def search_venue(
            ctx: RunContext[ResearchDeps],
            query: str,
            venue: str,
            max_results: int = 15,
        ) -> str:
            """
            Search for papers from a specific venue (conference or journal).

            Use this to find work from specific top venues.

            Args:
                query: Topic to search for
                venue: Venue name (e.g., "NeurIPS", "ICML", "ICLR", "Nature", "ACL", "CVPR")
                max_results: Maximum papers to return (1-20)

            Returns:
                Papers from that venue on the topic
            """
            max_results = min(max(1, max_results), 20)

            # Set activity before starting
            if ctx.deps.vibe_state and ctx.deps.project_path:
                ctx.deps.vibe_state.set_activity(f"Searching {venue} for '{query}'...")
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            s2_client = SemanticScholarClient(ctx.deps.http_client)

            try:
                papers = await s2_client.search_by_venue(query, venue, limit=max_results)
            except Exception as e:
                return f"Error searching venue: {str(e)}"

            if not papers:
                return f"No papers found at {venue} for: {query}"

            # Add to state if in vibe mode and save
            if ctx.deps.vibe_state:
                for paper in papers:
                    ctx.deps.vibe_state.add_paper(paper.to_dict(), source=f"venue:{venue}")
                if ctx.deps.project_path:
                    ctx.deps.vibe_state.save(ctx.deps.project_path)

            # Format results
            lines = [f"Found {len(papers)} papers from {venue} on '{query}':\n"]
            for i, paper in enumerate(papers, 1):
                year_str = f" ({paper.year})" if paper.year else ""
                lines.append(f"{i}. **{paper.title}**{year_str}")
                lines.append(f"   Citations: {paper.citation_count}")
                lines.append(f"   S2 ID: {paper.paper_id}")
                lines.append("")

            return "\n".join(lines)

        @agent.tool
        async def record_theme(
            ctx: RunContext[ResearchDeps],
            name: str,
            description: str,
            paper_ids: str,
        ) -> str:
            """
            Record an identified theme in the literature.

            Call this during SYNTHESIS to cluster papers by approach.

            Args:
                name: Short name for the theme (e.g., "Sparse Attention")
                description: Description of this approach and its characteristics
                paper_ids: Comma-separated list of paper IDs in this theme

            Returns:
                Confirmation with theme ID
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            # Set activity
            ctx.deps.vibe_state.set_activity(f"Recording theme: {name}...")

            ids = [p.strip() for p in paper_ids.split(",") if p.strip()]
            theme_id = ctx.deps.vibe_state.add_theme(name, description, ids)

            # Save state
            if ctx.deps.project_path:
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            return f"Theme recorded: {name} (ID: {theme_id}) with {len(ids)} papers"

        @agent.tool
        async def record_gap(
            ctx: RunContext[ResearchDeps],
            title: str,
            evidence: str,
            confidence: str = "medium",
        ) -> str:
            """
            Record an identified research gap.

            Call this during IDEATION when you find underexplored areas.

            Args:
                title: Short title for the gap
                evidence: What evidence suggests this is a gap?
                confidence: "low", "medium", or "high"

            Returns:
                Confirmation with gap ID
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            if confidence not in ("low", "medium", "high"):
                confidence = "medium"

            # Set activity
            ctx.deps.vibe_state.set_activity(f"Recording gap: {title}...")

            gap_id = ctx.deps.vibe_state.add_gap(title, evidence, confidence)

            # Save state
            if ctx.deps.project_path:
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            return f"Gap recorded: {title} (ID: {gap_id}, confidence: {confidence})"

        @agent.tool
        async def generate_hypothesis(
            ctx: RunContext[ResearchDeps],
            gap_id: str,
            title: str,
            description: str,
            rationale: str,
            building_blocks: str,
            suggested_experiments: str = "",
        ) -> str:
            """
            Generate a research hypothesis to address a gap.

            Args:
                gap_id: ID of the gap this addresses
                title: Short title for the hypothesis
                description: What is being proposed
                rationale: Why this could work
                building_blocks: Existing work to build upon
                suggested_experiments: How to test this

            Returns:
                Confirmation with hypothesis ID
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            # Set activity
            ctx.deps.vibe_state.set_activity(f"Generating hypothesis: {title}...")

            hypo_id = ctx.deps.vibe_state.add_hypothesis(
                gap_id=gap_id,
                title=title,
                description=description,
                rationale=rationale,
                building_blocks=building_blocks,
                suggested_experiments=suggested_experiments,
            )

            # Save state
            if ctx.deps.project_path:
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            return f"Hypothesis recorded: {title} (ID: {hypo_id})"

        @agent.tool
        async def score_hypothesis(
            ctx: RunContext[ResearchDeps],
            hypothesis_id: str,
            novelty: int,
            feasibility: int,
            impact: int,
            similar_work: str,
            differentiation: str,
        ) -> str:
            """
            Score and evaluate a hypothesis.

            Args:
                hypothesis_id: ID of the hypothesis to score
                novelty: 1-10 how novel is this idea
                feasibility: 1-10 how feasible to implement
                impact: 1-10 potential impact if successful
                similar_work: Most similar existing work
                differentiation: How this differs from existing work

            Returns:
                Confirmation with scores
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            # Set activity
            ctx.deps.vibe_state.set_activity(f"Scoring hypothesis {hypothesis_id}...")

            # Clamp scores
            novelty = max(1, min(10, novelty))
            feasibility = max(1, min(10, feasibility))
            impact = max(1, min(10, impact))

            success = ctx.deps.vibe_state.score_hypothesis(
                hypothesis_id=hypothesis_id,
                novelty=novelty,
                feasibility=feasibility,
                impact=impact,
                similar_work=similar_work,
                differentiation=differentiation,
            )

            if not success:
                return f"Error: Hypothesis {hypothesis_id} not found"

            # Save state
            if ctx.deps.project_path:
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            total = novelty + feasibility + impact
            return f"Hypothesis scored: N={novelty} F={feasibility} I={impact} (Total: {total}/30)"

        @agent.tool
        async def update_progress(
            ctx: RunContext[ResearchDeps],
            action: str,
            new_info_found: bool,
            phase_progress: int,
        ) -> str:
            """
            Update research progress after a significant action.

            IMPORTANT: Call this regularly to track progress and detect stalls.

            Args:
                action: What you just did
                new_info_found: Did this action yield new information?
                phase_progress: Estimated progress in current phase (0-100)

            Returns:
                Progress update, possibly with stall warning
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            warning = ctx.deps.vibe_state.update_progress(
                action=action,
                new_info=new_info_found,
                phase_progress=phase_progress,
            )

            # Save state
            if ctx.deps.project_path:
                ctx.deps.vibe_state.save(ctx.deps.project_path)

            state = ctx.deps.vibe_state
            msg = f"Progress: {state.current_phase.value.upper()} at {phase_progress}%"
            msg += f"\nPapers: {len(state.papers)} found, {len(state.papers_read)} read"
            msg += f"\nThemes: {len(state.themes)} | Gaps: {len(state.gaps)} | Hypotheses: {len(state.hypotheses)}"

            if warning:
                msg += f"\n\n{warning}"

            return msg

        @agent.tool
        async def advance_phase(
            ctx: RunContext[ResearchDeps],
            next_phase: str,
            summary: str,
        ) -> str:
            """
            Advance to the next research phase.

            Phases: scoping -> discovery -> synthesis -> ideation -> evaluation -> complete

            Args:
                next_phase: Phase to advance to
                summary: Summary of what was accomplished in current phase

            Returns:
                Confirmation of phase transition
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            try:
                phase = ResearchPhase(next_phase.lower())
            except ValueError:
                valid = ", ".join([p.value for p in ResearchPhase])
                return f"Error: Invalid phase '{next_phase}'. Valid phases: {valid}"

            # Set activity
            ctx.deps.vibe_state.set_activity(f"Advancing to {next_phase} phase...")

            current = ctx.deps.vibe_state.current_phase
            state = ctx.deps.vibe_state

            # Enforce minimum requirements for phase transitions
            if current == ResearchPhase.DISCOVERY and phase == ResearchPhase.SYNTHESIS:
                if len(state.papers) < 30:
                    return f"Cannot advance: Need at least 30 papers found (currently have {len(state.papers)}). Keep searching!"

            if current == ResearchPhase.SYNTHESIS and phase == ResearchPhase.IDEATION:
                papers_read = len(state.papers_read)
                themes_count = len(state.themes)
                issues = []
                if papers_read < 10:
                    issues.append(f"read at least 10 papers (currently {papers_read})")
                if themes_count < 3:
                    issues.append(f"record at least 3 themes (currently {themes_count})")
                if issues:
                    return f"Cannot advance: You need to {' and '.join(issues)}. Use `read_arxiv_paper` to read more papers!"

            success = state.advance_phase(phase)

            if not success:
                return f"Error: Cannot advance from {current.value} to {next_phase}. Follow the workflow order."

            # Save state
            if ctx.deps.project_path:
                state.save(ctx.deps.project_path)

            return f"Advanced to {next_phase.upper()} phase.\n\nPrevious phase ({current.value}) summary:\n{summary[:500]}"

        @agent.tool
        async def generate_report(
            ctx: RunContext[ResearchDeps],
        ) -> str:
            """
            Generate the final research report as a LaTeX document with citations.

            Call this in the EVALUATION phase after scoring hypotheses.

            Returns:
                Confirmation that report was generated
            """
            if not ctx.deps.vibe_state:
                return "Error: No vibe state available"

            state = ctx.deps.vibe_state

            # Generate summary-based filename from research findings
            state.finalize_report_slug()

            # Set activity
            state.set_activity("Generating final research report...")
            if ctx.deps.project_path:
                state.save(ctx.deps.project_path)

            ranked = state.get_ranked_hypotheses()

            # Helper to escape LaTeX special characters
            def escape_latex(text: str) -> str:
                if not text:
                    return ""
                replacements = [
                    ('\\', r'\textbackslash{}'),
                    ('&', r'\&'),
                    ('%', r'\%'),
                    ('$', r'\$'),
                    ('#', r'\#'),
                    ('_', r'\_'),
                    ('{', r'\{'),
                    ('}', r'\}'),
                    ('~', r'\textasciitilde{}'),
                    ('^', r'\textasciicircum{}'),
                ]
                for old, new in replacements:
                    text = text.replace(old, new)
                return text

            # Helper to create citation key from paper
            def make_cite_key(paper: dict) -> str:
                authors = paper.get('authors', [])
                first_author = authors[0].split()[-1] if authors else 'unknown'
                year = paper.get('year', 'nd')
                # Clean the key
                key = f"{first_author}{year}".lower()
                key = ''.join(c for c in key if c.isalnum())
                return key

            # Helper to strip version number from paper ID (e.g., "2410.07348v1" -> "2410.07348")
            def strip_version(paper_id: str) -> str:
                import re
                return re.sub(r'v\d+$', '', paper_id)

            # Build BibTeX entries
            bib_entries = []
            cite_keys = {}  # paper_id -> cite_key
            cite_keys_by_base = {}  # base_paper_id (no version) -> cite_key

            for paper in state.papers:
                paper_id = paper.get('paper_id', '')
                if not paper_id:
                    continue

                cite_key = make_cite_key(paper)
                # Handle duplicates
                base_key = cite_key
                counter = 1
                while cite_key in cite_keys.values():
                    cite_key = f"{base_key}{chr(ord('a') + counter - 1)}"
                    counter += 1

                cite_keys[paper_id] = cite_key
                # Also map base ID (without version) for flexible lookup
                base_id = strip_version(paper_id)
                if base_id not in cite_keys_by_base:
                    cite_keys_by_base[base_id] = cite_key

                authors = paper.get('authors', [])
                author_str = ' and '.join(authors[:5])
                if len(authors) > 5:
                    author_str += ' and others'

                title = paper.get('title', 'Unknown Title')
                year = paper.get('year', '')
                abstract = paper.get('abstract', '')[:500]

                bib_entry = f"""@article{{{cite_key},
  author = {{{author_str}}},
  title = {{{title}}},
  year = {{{year}}},
  note = {{Paper ID: {paper_id}}}
}}"""
                bib_entries.append(bib_entry)

            # Build LaTeX document
            topic_escaped = escape_latex(state.topic)
            date_str = datetime.now().strftime('%B %d, %Y')

            latex_lines = [
                r"\documentclass[11pt,a4paper]{article}",
                r"\usepackage[utf8]{inputenc}",
                r"\usepackage[T1]{fontenc}",
                r"\usepackage{lmodern}",
                r"\usepackage[margin=1in]{geometry}",
                r"\usepackage{hyperref}",
                r"\usepackage{natbib}",
                r"\usepackage{booktabs}",
                r"\usepackage{enumitem}",
                r"\usepackage{xcolor}",
                r"",
                r"\definecolor{hypoblue}{RGB}{0,102,204}",
                r"\definecolor{gapred}{RGB}{204,51,51}",
                r"",
                r"\title{Vibe Research Report:\\",
                f"  {topic_escaped}}}",
                r"\author{Generated by Aura Vibe Research}",
                f"\\date{{{date_str}}}",
                r"",
                r"\begin{document}",
                r"\maketitle",
                r"",
                r"\begin{abstract}",
                f"This report presents the findings of an automated literature review on \\textbf{{{topic_escaped}}}. ",
                f"We analyzed {len(state.papers)} papers, identified {len(state.themes)} major themes, ",
                f"discovered {len(state.gaps)} research gaps, and generated {len(state.hypotheses)} novel research hypotheses.",
                r"\end{abstract}",
                r"",
                r"\tableofcontents",
                r"\newpage",
                r"",
            ]

            # Research Scope
            if state.scope:
                latex_lines.extend([
                    r"\section{Research Scope}",
                    r"",
                    r"\begin{itemize}",
                    f"  \\item \\textbf{{Domain}}: {escape_latex(state.scope.get('domain', 'General'))}",
                    f"  \\item \\textbf{{Constraints}}: {escape_latex(state.scope.get('constraints', 'None specified'))}",
                    f"  \\item \\textbf{{Goal}}: {escape_latex(state.scope.get('goal', 'Exploration'))}",
                ])
                if state.scope.get('notes'):
                    latex_lines.append(f"  \\item \\textbf{{Notes}}: {escape_latex(state.scope.get('notes'))}")
                latex_lines.extend([
                    r"\end{itemize}",
                    r"",
                ])

            # Literature Landscape (Themes)
            if state.themes:
                latex_lines.extend([
                    r"\section{Literature Landscape}",
                    r"",
                ])
                for theme in state.themes:
                    theme_name = escape_latex(theme.get('name', 'Unnamed Theme'))
                    theme_desc = escape_latex(theme.get('description', ''))
                    paper_ids = theme.get('paper_ids', [])

                    latex_lines.extend([
                        f"\\subsection{{{theme_name}}}",
                        r"",
                        theme_desc,
                        r"",
                    ])

                    # Add citations for papers in this theme (try exact match first, then base ID)
                    valid_cites = []
                    for pid in paper_ids:
                        cite_key = cite_keys.get(pid) or cite_keys_by_base.get(strip_version(pid))
                        if cite_key and cite_key not in valid_cites:
                            valid_cites.append(cite_key)
                    if valid_cites:
                        cite_str = ', '.join(valid_cites[:10])  # Limit citations
                        latex_lines.append(f"Key works in this area include \\cite{{{cite_str}}}.")
                        latex_lines.append(r"")

            # Research Gaps
            if state.gaps:
                latex_lines.extend([
                    r"\section{Identified Research Gaps}",
                    r"",
                ])
                for gap in state.gaps:
                    gap_title = escape_latex(gap.get('title', 'Unnamed Gap'))
                    gap_evidence = escape_latex(gap.get('evidence', ''))
                    confidence = gap.get('confidence', 'medium').upper()

                    latex_lines.extend([
                        f"\\subsection{{\\textcolor{{gapred}}{{{gap_title}}}}}",
                        r"",
                        f"\\textbf{{Confidence}}: {confidence}",
                        r"",
                        gap_evidence,
                        r"",
                    ])

            # Hypotheses
            if ranked:
                latex_lines.extend([
                    r"\section{Research Hypotheses}",
                    r"",
                    r"The following hypotheses are ranked by total score (Novelty + Feasibility + Impact).",
                    r"",
                ])
                for i, hypo in enumerate(ranked, 1):
                    n = hypo.get('novelty_score', 0)
                    f_score = hypo.get('feasibility_score', 0)
                    imp = hypo.get('impact_score', 0)
                    total = n + f_score + imp

                    title = escape_latex(hypo.get('title', 'Untitled'))
                    desc = escape_latex(hypo.get('description', ''))
                    rationale = escape_latex(hypo.get('rationale', ''))
                    building = escape_latex(hypo.get('building_blocks', ''))
                    experiments = escape_latex(hypo.get('suggested_experiments', ''))
                    similar = escape_latex(hypo.get('similar_work', ''))
                    diff = escape_latex(hypo.get('differentiation', ''))

                    latex_lines.extend([
                        f"\\subsection{{\\textcolor{{hypoblue}}{{Hypothesis {i}: {title}}}}}",
                        r"",
                        r"\begin{tabular}{lccc}",
                        r"\toprule",
                        r"Novelty & Feasibility & Impact & \textbf{Total} \\",
                        r"\midrule",
                        f"{n}/10 & {f_score}/10 & {imp}/10 & \\textbf{{{total}/30}} \\\\",
                        r"\bottomrule",
                        r"\end{tabular}",
                        r"",
                        r"\paragraph{Description}",
                        desc,
                        r"",
                        r"\paragraph{Rationale}",
                        rationale,
                        r"",
                        r"\paragraph{Building Blocks}",
                        building,
                        r"",
                    ])
                    if experiments:
                        latex_lines.extend([
                            r"\paragraph{Suggested Experiments}",
                            experiments,
                            r"",
                        ])
                    if similar:
                        latex_lines.extend([
                            r"\paragraph{Similar Work}",
                            similar,
                            r"",
                        ])
                    if diff:
                        latex_lines.extend([
                            r"\paragraph{Differentiation}",
                            diff,
                            r"",
                        ])

            # Bibliography
            # Use the report filename for bibliography reference
            report_base = state.get_report_filename()
            latex_lines.extend([
                r"",
                r"\bibliographystyle{plainnat}",
                f"\\bibliography{{{report_base}}}",
                r"",
                r"\end{document}",
            ])

            report_tex = "\n".join(latex_lines)
            report_bib = "\n\n".join(bib_entries)

            # Save state
            state.report = report_tex
            state.is_complete = True
            state.current_phase = ResearchPhase.COMPLETE

            # Save files
            if ctx.deps.project_path:
                from pathlib import Path

                state.save(ctx.deps.project_path)

                # Use topic-based filename from state
                base_filename = state.get_report_filename()

                # Create subdirectory for this research: report/<base_filename>/
                report_dir = Path(ctx.deps.project_path) / "report" / base_filename
                report_dir.mkdir(parents=True, exist_ok=True)

                # Save .tex file
                tex_filename = f"{base_filename}.tex"
                tex_path = report_dir / tex_filename
                tex_path.write_text(report_tex, encoding="utf-8")

                # Save .bib file
                bib_filename = f"{base_filename}.bib"
                bib_path = report_dir / bib_filename
                bib_path.write_text(report_bib, encoding="utf-8")

                logger.info(f"Report saved to: {tex_path}")
                logger.info(f"Bibliography saved to: {bib_path}")

                return f"Report generated successfully!\n\nFiles created:\n- report/{base_filename}/{tex_filename}\n- report/{base_filename}/{bib_filename}\n\nThe report includes {len(bib_entries)} citations from the analyzed papers."

            return "Report generated but could not save files (no project path)"

        @agent.tool
        async def save_to_memory(
            ctx: RunContext[ResearchDeps],
            entry_type: str,
            title: str,
            content: str,
            tags: str = "",
        ) -> str:
            """
            Save a finding to project memory for future sessions.

            Args:
                entry_type: Type of entry ("paper", "gap", "hypothesis", "note")
                title: Short title for the entry
                content: Full content
                tags: Comma-separated tags

            Returns:
                Confirmation
            """
            if not ctx.deps.project_path:
                return "No project path - cannot save to memory"

            try:
                from services.memory import MemoryService

                svc = MemoryService(ctx.deps.project_path)
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                tag_list.append(entry_type)

                if entry_type == "paper":
                    # Save as paper entry
                    svc.add_entry("papers", {
                        "title": title,
                        "authors": [],
                        "summary": content,
                        "tags": tag_list,
                        "arxiv_id": "",
                    })
                else:
                    # Save as note
                    svc.add_entry("notes", {
                        "content": f"[{entry_type.upper()}] {title}\n\n{content}",
                        "tags": tag_list,
                    })

                return f"Saved to memory: [{entry_type}] {title}"

            except Exception as e:
                return f"Error saving to memory: {str(e)}"
