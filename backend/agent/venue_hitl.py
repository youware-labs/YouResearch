"""
Research Preference HITL (Human-in-the-Loop) System

Provides a two-step blocking mechanism for the research agent:
1. Domain selection - system suggests domain, user confirms/changes
2. Venue selection - system suggests venues for domain, user selects

Flow:
1. Research agent calls `request_research_preferences()`
2. Manager requests domain preference → Frontend shows domain modal
3. User confirms/selects domain
4. Manager uses LLM to suggest venues for that domain
5. Manager requests venue preference → Frontend shows venue modal
6. User selects venues
7. Research agent continues with filters applied
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DomainPreferenceRequest:
    """A pending domain preference request."""
    request_id: str
    topic: str
    session_id: str
    suggested_domain: str = ""

    # Result when resolved
    domain: str = ""
    resolved: bool = False

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "topic": self.topic,
            "session_id": self.session_id,
            "suggested_domain": self.suggested_domain,
            "domain": self.domain,
            "resolved": self.resolved,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class VenuePreferenceRequest:
    """A pending venue preference request."""
    request_id: str
    topic: str
    domain: str
    session_id: str
    suggested_venues: list[str] = field(default_factory=list)

    # Result when resolved
    venues: list[str] = field(default_factory=list)
    resolved: bool = False

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "topic": self.topic,
            "domain": self.domain,
            "session_id": self.session_id,
            "suggested_venues": self.suggested_venues,
            "venues": self.venues,
            "resolved": self.resolved,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class ResearchPreferences:
    """Complete research preferences after both HITL steps."""
    domain: str
    venues: list[str]


# =============================================================================
# LLM-based Suggestion Functions
# =============================================================================

async def suggest_domain_with_llm(topic: str) -> str:
    """
    Use LLM to suggest a research domain based on the topic.

    Returns a domain like "Computer Science", "Life Sciences", "Physics", etc.
    """
    from agent.providers import get_haiku_model
    from pydantic_ai import Agent

    agent = Agent(
        model=get_haiku_model(),
        system_prompt="""You are a research domain classifier. Given a research topic,
identify the most appropriate academic domain/field.

Respond with ONLY the domain name, nothing else. Examples:
- "Computer Science"
- "Machine Learning"
- "Natural Language Processing"
- "Computer Vision"
- "Life Sciences"
- "Biology"
- "Physiology"
- "Neuroscience"
- "Medicine"
- "Chemistry"
- "Physics"
- "Mathematics"
- "Economics"
- "Psychology"
- "Materials Science"
- "Environmental Science"

Be specific when possible (e.g., "Neuroscience" rather than just "Biology").""",
    )

    try:
        result = await agent.run(f"Research topic: {topic}")
        domain = result.output.strip().strip('"').strip("'")
        logger.info(f"LLM suggested domain '{domain}' for topic '{topic}'")
        return domain
    except Exception as e:
        logger.error(f"Failed to suggest domain: {e}")
        return "General Science"


async def suggest_venues_with_llm(topic: str, domain: str) -> list[str]:
    """
    Use LLM to suggest relevant venues (conferences/journals) based on domain and topic.

    The LLM dynamically reasons about the best venues - no hardcoded options.

    Returns a list of venue names.
    """
    from agent.providers import get_haiku_model
    from pydantic_ai import Agent

    agent = Agent(
        model=get_haiku_model(),
        system_prompt="""You are an academic venue expert. Given a research domain and specific topic,
reason about and suggest the MOST RELEVANT conferences and journals where papers on this topic are typically published.

Your task:
1. Analyze the domain and topic carefully
2. Think about which specific conferences and journals publish papers on this exact topic
3. Consider both top-tier venues AND specialized venues for the topic
4. Include a mix of conferences and journals

Guidelines:
- Be SPECIFIC to the topic, not just the broad domain
- For ML topics like "world models" or "transformers" → suggest ML venues (NeurIPS, ICML, ICLR, etc.)
- For robotics-related topics → include robotics venues (ICRA, CoRL, RSS, etc.)
- For interdisciplinary topics → include venues from multiple relevant fields
- Avoid generic venues (Nature, Science) unless the topic truly spans multiple fields

Respond with ONLY a JSON array of 8-12 venue names. No explanation, no markdown, just the JSON array.

Example output: ["NeurIPS", "ICML", "ICLR", "CoRL", "AAAI", "JMLR", "Nature Machine Intelligence", "RSS"]""",
    )

    try:
        prompt = f"""Domain: {domain}
Research topic: {topic}

Based on this domain and topic, what are the most relevant academic venues (conferences and journals)?"""

        result = await agent.run(prompt)

        # Parse JSON array from response
        import json
        response = result.output.strip()

        # Handle markdown code blocks
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])

        # Handle potential "json" language tag
        if response.startswith("json"):
            response = response[4:].strip()

        venues = json.loads(response)
        if isinstance(venues, list) and len(venues) > 0:
            venues = [v for v in venues if isinstance(v, str) and v.strip()]
            logger.info(f"LLM suggested {len(venues)} venues for '{domain}' + '{topic[:50]}...': {venues}")
            return venues[:12]
    except Exception as e:
        logger.error(f"Failed to suggest venues via LLM: {e}")

    # If LLM fails completely, return empty list - user can add custom venues
    logger.warning(f"LLM venue suggestion failed for domain '{domain}', returning empty list")
    return []


# =============================================================================
# Research Preference Manager
# =============================================================================

class ResearchPreferenceManager:
    """
    Manager for two-step research preference HITL workflow.

    Step 1: Domain selection
    Step 2: Venue selection (with LLM-suggested venues for the domain)
    """

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout

        # Pending requests by request_id
        self._domain_pending: dict[str, DomainPreferenceRequest] = {}
        self._venue_pending: dict[str, VenuePreferenceRequest] = {}

        # Events for async waiting
        self._domain_events: dict[str, asyncio.Event] = {}
        self._venue_events: dict[str, asyncio.Event] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Callbacks for emitting events (set by streaming runner)
        self._domain_event_callback: Optional[Callable] = None
        self._venue_event_callback: Optional[Callable] = None

    def set_domain_event_callback(self, callback: Callable):
        """Set callback for emitting domain preference request events."""
        self._domain_event_callback = callback

    def set_venue_event_callback(self, callback: Callable):
        """Set callback for emitting venue preference request events."""
        self._venue_event_callback = callback

    async def request_research_preferences(
        self,
        topic: str,
        session_id: str,
    ) -> ResearchPreferences:
        """
        Request complete research preferences through two-step HITL.

        1. Request domain preference (with LLM suggestion)
        2. Request venue preference (with LLM-generated venues for domain)

        Args:
            topic: The research topic
            session_id: Session identifier

        Returns:
            ResearchPreferences with domain and venues
        """
        # Step 1: Get domain preference
        domain = await self._request_domain_preference(topic, session_id)

        if not domain:
            # User skipped or timeout - use suggested domain
            domain = await suggest_domain_with_llm(topic)

        # Step 2: Get venue preferences (with LLM suggestions for this domain)
        venues = await self._request_venue_preference(topic, domain, session_id)

        return ResearchPreferences(domain=domain, venues=venues)

    async def _request_domain_preference(
        self,
        topic: str,
        session_id: str,
    ) -> str:
        """Request domain preference from user."""
        request_id = str(uuid.uuid4())

        # Get LLM suggestion
        suggested_domain = await suggest_domain_with_llm(topic)

        request = DomainPreferenceRequest(
            request_id=request_id,
            topic=topic,
            session_id=session_id,
            suggested_domain=suggested_domain,
        )

        async with self._lock:
            self._domain_pending[request_id] = request
            self._domain_events[request_id] = asyncio.Event()

        logger.info(f"DomainHITL: Requesting domain for topic '{topic[:50]}...' (suggested: {suggested_domain})")

        # Emit event to notify frontend
        if self._domain_event_callback:
            await self._domain_event_callback(request)

        # Wait for response or timeout
        try:
            await asyncio.wait_for(
                self._domain_events[request_id].wait(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"DomainHITL: Request timeout for {request_id}")
            async with self._lock:
                if request_id in self._domain_pending:
                    request = self._domain_pending[request_id]
                    request.resolved = True
                    request.domain = suggested_domain  # Use suggestion on timeout
                    request.resolved_at = datetime.now(timezone.utc)

        # Cleanup and return
        async with self._lock:
            self._domain_events.pop(request_id, None)
            result = self._domain_pending.pop(request_id, request)

        logger.info(f"DomainHITL: Request {request_id} resolved with domain: {result.domain}")
        return result.domain

    async def _request_venue_preference(
        self,
        topic: str,
        domain: str,
        session_id: str,
    ) -> list[str]:
        """Request venue preferences from user."""
        request_id = str(uuid.uuid4())

        # Get LLM-suggested venues for this domain
        suggested_venues = await suggest_venues_with_llm(topic, domain)

        request = VenuePreferenceRequest(
            request_id=request_id,
            topic=topic,
            domain=domain,
            session_id=session_id,
            suggested_venues=suggested_venues,
        )

        async with self._lock:
            self._venue_pending[request_id] = request
            self._venue_events[request_id] = asyncio.Event()

        logger.info(f"VenueHITL: Requesting venues for domain '{domain}' ({len(suggested_venues)} suggestions)")

        # Emit event to notify frontend
        if self._venue_event_callback:
            await self._venue_event_callback(request)

        # Wait for response or timeout
        try:
            await asyncio.wait_for(
                self._venue_events[request_id].wait(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"VenueHITL: Request timeout for {request_id}")
            async with self._lock:
                if request_id in self._venue_pending:
                    request = self._venue_pending[request_id]
                    request.resolved = True
                    request.venues = []  # Empty = no filter
                    request.resolved_at = datetime.now(timezone.utc)

        # Cleanup and return
        async with self._lock:
            self._venue_events.pop(request_id, None)
            result = self._venue_pending.pop(request_id, request)

        logger.info(f"VenueHITL: Request {request_id} resolved with venues: {result.venues}")
        return result.venues

    async def submit_domain_preference(
        self,
        request_id: str,
        domain: str,
    ) -> bool:
        """Submit domain preference for a pending request."""
        async with self._lock:
            if request_id not in self._domain_pending:
                logger.warning(f"DomainHITL: Cannot resolve unknown request {request_id}")
                return False

            request = self._domain_pending[request_id]
            request.domain = domain
            request.resolved = True
            request.resolved_at = datetime.now(timezone.utc)

            if request_id in self._domain_events:
                self._domain_events[request_id].set()

            logger.info(f"DomainHITL: User selected domain: {domain}")
            return True

    async def submit_venue_preferences(
        self,
        request_id: str,
        venues: list[str],
    ) -> bool:
        """Submit venue preferences for a pending request."""
        async with self._lock:
            if request_id not in self._venue_pending:
                logger.warning(f"VenueHITL: Cannot resolve unknown request {request_id}")
                return False

            request = self._venue_pending[request_id]
            request.venues = venues
            request.resolved = True
            request.resolved_at = datetime.now(timezone.utc)

            if request_id in self._venue_events:
                self._venue_events[request_id].set()

            logger.info(f"VenueHITL: User selected venues: {venues}")
            return True

    async def get_pending_domain(self, session_id: str | None = None) -> list[DomainPreferenceRequest]:
        """Get pending domain requests."""
        async with self._lock:
            requests = [req for req in self._domain_pending.values() if not req.resolved]
            if session_id:
                requests = [r for r in requests if r.session_id == session_id]
            return requests

    async def get_pending_venue(self, session_id: str | None = None) -> list[VenuePreferenceRequest]:
        """Get pending venue requests."""
        async with self._lock:
            requests = [req for req in self._venue_pending.values() if not req.resolved]
            if session_id:
                requests = [r for r in requests if r.session_id == session_id]
            return requests


# =============================================================================
# Singleton Manager
# =============================================================================

_default_manager: ResearchPreferenceManager | None = None


def get_research_preference_manager() -> ResearchPreferenceManager:
    """Get or create the default research preference manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ResearchPreferenceManager()
    return _default_manager


def reset_research_preference_manager():
    """Reset the research preference manager (for testing)."""
    global _default_manager
    _default_manager = None


# =============================================================================
# Backwards Compatibility (deprecated)
# =============================================================================

def get_venue_preference_manager():
    """Deprecated: Use get_research_preference_manager instead."""
    return get_research_preference_manager()
