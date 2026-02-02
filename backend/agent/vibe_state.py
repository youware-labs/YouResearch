"""
Vibe Research State Management

Tracks research progress using a dual-ledger pattern inspired by Magentic-One:
- Task Ledger: What we're researching, what we've found
- Progress Ledger: Current phase, progress %, stall detection

This state is injected into the agent's system prompt and updated via tools.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


def generate_slug(topic: str, max_length: int = 50) -> str:
    """
    Generate a filesystem-safe slug from a research topic.

    Args:
        topic: The research topic string
        max_length: Maximum length of the slug

    Returns:
        A lowercase, hyphen-separated slug suitable for filenames
    """
    if not topic:
        return "untitled"

    # Lowercase and replace common separators with spaces
    slug = topic.lower()
    slug = re.sub(r'[/\\:,;]', ' ', slug)

    # Remove non-alphanumeric characters except spaces and hyphens
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)

    # Replace whitespace with hyphens
    slug = re.sub(r'\s+', '-', slug.strip())

    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Truncate to max length, but don't cut in the middle of a word
    if len(slug) > max_length:
        slug = slug[:max_length]
        # Try to end at a word boundary
        if '-' in slug:
            slug = slug.rsplit('-', 1)[0]

    return slug.strip('-') or "untitled"


class ResearchPhase(str, Enum):
    """Phases of vibe research workflow."""
    SCOPING = "scoping"       # Clarify requirements
    DISCOVERY = "discovery"   # Search and find papers
    SYNTHESIS = "synthesis"   # Read and identify themes
    IDEATION = "ideation"     # Find gaps, generate hypotheses
    EVALUATION = "evaluation" # Score and rank hypotheses
    COMPLETE = "complete"     # Report generated


@dataclass
class VibeResearchState:
    """
    Complete state for a vibe research session.

    Implements the dual-ledger pattern:
    - Task Ledger: topic, scope, papers, themes, gaps, hypotheses
    - Progress Ledger: phase, progress, stall detection
    """

    # === IDENTITY ===
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    report_slug: str = ""  # Generated from topic, used for output filenames

    # === TASK LEDGER ===
    topic: str = ""
    scope: dict = field(default_factory=dict)  # Clarified parameters

    # Discovered content
    papers: list[dict] = field(default_factory=list)
    themes: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    hypotheses: list[dict] = field(default_factory=list)

    # Papers read in full (IDs)
    papers_read: list[str] = field(default_factory=list)

    # === PROGRESS LEDGER ===
    current_phase: ResearchPhase = ResearchPhase.SCOPING
    phase_progress: dict = field(default_factory=dict)  # {phase: percent}
    last_action: str = ""
    current_activity: str = ""  # What the agent is currently doing
    updated_at: str = ""  # Last state update timestamp
    stall_count: int = 0
    action_history: list[str] = field(default_factory=list)

    # === OUTPUT ===
    report: str = ""
    is_complete: bool = False

    # === CONFIGURATION ===
    max_papers: int = 100
    max_papers_to_read: int = 30
    target_hypotheses: int = 5

    def __post_init__(self):
        """Auto-generate report_slug from topic if not provided."""
        if self.topic and not self.report_slug:
            self.report_slug = generate_slug(self.topic)

    def set_topic(self, topic: str) -> None:
        """Set the research topic and generate the report slug."""
        self.topic = topic
        self.report_slug = generate_slug(topic)

    def generate_summary_title(self) -> str:
        """
        Generate a descriptive summary title from research findings.

        Uses themes, scope, and topic to create a meaningful title
        that reflects what was actually researched.
        """
        parts = []

        # Use top themes if available (most descriptive of actual findings)
        if self.themes:
            # Get up to 2 theme names
            theme_names = [t.get('name', '') for t in self.themes[:2] if t.get('name')]
            if theme_names:
                parts.extend(theme_names)

        # Add scope domain if available and not redundant
        if self.scope and self.scope.get('domain'):
            domain = self.scope.get('domain', '')
            # Only add if not already covered by themes
            if domain and not any(domain.lower() in p.lower() for p in parts):
                parts.append(domain)

        # Fall back to topic if nothing else
        if not parts and self.topic:
            return self.topic

        # Combine parts into a title
        if parts:
            return ' - '.join(parts[:3])  # Limit to 3 parts

        return self.topic or "Research Report"

    def finalize_report_slug(self) -> None:
        """
        Generate and set the report slug based on research findings.

        Call this when the research is complete to get a descriptive filename.
        """
        summary = self.generate_summary_title()
        self.report_slug = generate_slug(summary)

    def get_report_filename(self) -> str:
        """Get the base filename for report files (without extension)."""
        if self.report_slug:
            return self.report_slug
        # Fallback to session_id if no slug
        return f"vibe_research_{self.session_id}"

    def add_paper(self, paper: dict, source: str = "") -> str:
        """Add a paper to the discovered list."""
        paper_id = paper.get("paper_id", str(uuid.uuid4())[:8])

        # Check for duplicates by ID or title
        for p in self.papers:
            if p.get("paper_id") == paper_id:
                return p.get("paper_id", "")
            # Also check by title (case-insensitive, first 50 chars)
            if p.get("title", "").lower()[:50] == paper.get("title", "").lower()[:50]:
                return p.get("paper_id", "")

        paper["source"] = source
        paper["paper_id"] = paper_id
        self.papers.append(paper)
        return paper_id

    def add_theme(self, name: str, description: str, paper_ids: list[str]) -> str:
        """Add an identified theme."""
        theme_id = str(uuid.uuid4())[:8]
        self.themes.append({
            "theme_id": theme_id,
            "name": name,
            "description": description,
            "paper_ids": paper_ids,
        })
        return theme_id

    def add_gap(self, title: str, evidence: str, confidence: str) -> str:
        """Add an identified gap."""
        gap_id = str(uuid.uuid4())[:8]
        self.gaps.append({
            "gap_id": gap_id,
            "title": title,
            "evidence": evidence,
            "confidence": confidence,
        })
        return gap_id

    def add_hypothesis(
        self,
        gap_id: str,
        title: str,
        description: str,
        rationale: str,
        building_blocks: str,
        suggested_experiments: str = "",
    ) -> str:
        """Add a generated hypothesis."""
        hypo_id = str(uuid.uuid4())[:8]
        self.hypotheses.append({
            "hypothesis_id": hypo_id,
            "gap_id": gap_id,
            "title": title,
            "description": description,
            "rationale": rationale,
            "building_blocks": building_blocks,
            "suggested_experiments": suggested_experiments,
            "novelty_score": 0,
            "feasibility_score": 0,
            "impact_score": 0,
            "similar_work": "",
            "differentiation": "",
        })
        return hypo_id

    def score_hypothesis(
        self,
        hypothesis_id: str,
        novelty: int,
        feasibility: int,
        impact: int,
        similar_work: str = "",
        differentiation: str = "",
    ) -> bool:
        """Score a hypothesis."""
        for h in self.hypotheses:
            if h.get("hypothesis_id") == hypothesis_id:
                h["novelty_score"] = novelty
                h["feasibility_score"] = feasibility
                h["impact_score"] = impact
                h["similar_work"] = similar_work
                h["differentiation"] = differentiation
                return True
        return False

    def update_progress(
        self,
        action: str,
        new_info: bool,
        phase_progress: int,
    ) -> str:
        """
        Update progress after an action.

        Returns warning message if stalled.
        """
        self.last_action = action
        self.action_history.append(f"[{datetime.now().strftime('%H:%M')}] {action}")

        # Keep only last 50 actions
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]

        self.phase_progress[self.current_phase.value] = phase_progress

        if new_info:
            self.stall_count = 0
        else:
            self.stall_count += 1

        if self.stall_count >= 3:
            return "WARNING: Progress stalled. Consider changing strategy or advancing to next phase."

        return ""

    def set_activity(self, activity: str) -> None:
        """Set the current activity and update timestamp."""
        self.current_activity = activity
        self.updated_at = datetime.now().isoformat()

    def clear_activity(self) -> None:
        """Clear the current activity."""
        self.current_activity = ""
        self.updated_at = datetime.now().isoformat()

    def advance_phase(self, next_phase: ResearchPhase) -> bool:
        """Advance to next phase."""
        valid_transitions = {
            ResearchPhase.SCOPING: [ResearchPhase.DISCOVERY],
            ResearchPhase.DISCOVERY: [ResearchPhase.SYNTHESIS],
            ResearchPhase.SYNTHESIS: [ResearchPhase.IDEATION],
            ResearchPhase.IDEATION: [ResearchPhase.EVALUATION],
            ResearchPhase.EVALUATION: [ResearchPhase.COMPLETE],
        }

        if next_phase in valid_transitions.get(self.current_phase, []):
            self.current_phase = next_phase
            self.stall_count = 0
            return True
        return False

    def get_ranked_hypotheses(self) -> list[dict]:
        """Get hypotheses ranked by combined score."""
        def score(h):
            return (
                h.get("novelty_score", 0) +
                h.get("feasibility_score", 0) +
                h.get("impact_score", 0)
            )
        return sorted(self.hypotheses, key=score, reverse=True)

    def to_context(self) -> str:
        """Format state as context for injection into system prompt."""
        papers_summary = f"{len(self.papers)} found, {len(self.papers_read)} read in detail"
        themes_list = "\n".join(
            f"  - {t['name']}: {t['description'][:100]}"
            for t in self.themes[:5]
        ) or "  (none yet)"
        gaps_list = "\n".join(
            f"  - [{g['confidence'].upper()}] {g['title']}"
            for g in self.gaps[:5]
        ) or "  (none yet)"
        hypo_list = "\n".join(
            f"  - {h['title']} (scores: N={h.get('novelty_score', '?')}/F={h.get('feasibility_score', '?')}/I={h.get('impact_score', '?')})"
            for h in self.get_ranked_hypotheses()[:5]
        ) or "  (none yet)"

        return f"""
## Current Research State

**Session**: {self.session_id}
**Topic**: {self.topic}
**Phase**: {self.current_phase.value.upper()}
**Progress**: {self.phase_progress.get(self.current_phase.value, 0)}%
**Stall Count**: {self.stall_count}/3

### Scope
{json.dumps(self.scope, indent=2) if self.scope else "(not yet defined)"}

### Papers
{papers_summary}

### Themes Identified
{themes_list}

### Research Gaps
{gaps_list}

### Hypotheses
{hypo_list}

### Last Action
{self.last_action or "(none)"}
"""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "report_slug": self.report_slug,
            "topic": self.topic,
            "scope": self.scope,
            "papers": self.papers,
            "papers_read": self.papers_read,
            "themes": self.themes,
            "gaps": self.gaps,
            "hypotheses": self.hypotheses,
            "current_phase": self.current_phase.value,
            "phase_progress": self.phase_progress,
            "last_action": self.last_action,
            "current_activity": self.current_activity,
            "updated_at": self.updated_at,
            "stall_count": self.stall_count,
            "action_history": self.action_history,
            "is_complete": self.is_complete,
            "report": self.report,
            "max_papers": self.max_papers,
            "max_papers_to_read": self.max_papers_to_read,
            "target_hypotheses": self.target_hypotheses,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VibeResearchState":
        """Deserialize from dictionary."""
        topic = data.get("topic", "")
        # Generate slug from topic if not present (backward compatibility)
        report_slug = data.get("report_slug") or generate_slug(topic) if topic else ""

        state = cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:8]),
            created_at=data.get("created_at", datetime.now().isoformat()),
            report_slug=report_slug,
            topic=topic,
            scope=data.get("scope", {}),
            papers=data.get("papers", []),
            papers_read=data.get("papers_read", []),
            themes=data.get("themes", []),
            gaps=data.get("gaps", []),
            hypotheses=data.get("hypotheses", []),
            phase_progress=data.get("phase_progress", {}),
            last_action=data.get("last_action", ""),
            current_activity=data.get("current_activity", ""),
            updated_at=data.get("updated_at", ""),
            stall_count=data.get("stall_count", 0),
            action_history=data.get("action_history", []),
            is_complete=data.get("is_complete", False),
            report=data.get("report", ""),
            max_papers=data.get("max_papers", 100),
            max_papers_to_read=data.get("max_papers_to_read", 30),
            target_hypotheses=data.get("target_hypotheses", 5),
        )
        try:
            state.current_phase = ResearchPhase(data.get("current_phase", "scoping"))
        except ValueError:
            state.current_phase = ResearchPhase.SCOPING
        return state

    def save(self, project_path: str) -> None:
        """Save state to project's .aura directory."""
        aura_dir = Path(project_path) / ".aura"
        aura_dir.mkdir(exist_ok=True)

        state_file = aura_dir / f"vibe_research_{self.session_id}.json"
        state_file.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, project_path: str, session_id: str) -> Optional["VibeResearchState"]:
        """Load state from project's .aura directory."""
        state_file = Path(project_path) / ".aura" / f"vibe_research_{session_id}.json"
        if not state_file.exists():
            return None

        try:
            data = json.loads(state_file.read_text())
            return cls.from_dict(data)
        except Exception:
            return None

    @classmethod
    def list_sessions(cls, project_path: str) -> list[dict]:
        """List all vibe research sessions for a project."""
        aura_dir = Path(project_path) / ".aura"
        sessions = []

        if aura_dir.exists():
            for f in aura_dir.glob("vibe_research_*.json"):
                try:
                    session_id = f.stem.replace("vibe_research_", "")
                    state = cls.load(project_path, session_id)
                    if state:
                        sessions.append({
                            "session_id": state.session_id,
                            "topic": state.topic,
                            "current_phase": state.current_phase.value,
                            "is_complete": state.is_complete,
                            "created_at": state.created_at,
                            "papers_count": len(state.papers),
                            "hypotheses_count": len(state.hypotheses),
                        })
                except Exception:
                    pass

        return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)
