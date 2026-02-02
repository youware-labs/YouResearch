"""
Memory Service

Manages project memory stored in .aura/memory.json
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass, asdict, field


# Entry types
EntryType = Literal["papers", "citations", "conventions", "todos", "notes"]

# Token estimation: ~4 chars per token for English text
CHARS_PER_TOKEN = 4
TOKEN_WARNING_THRESHOLD = 4000


@dataclass
class PaperEntry:
    id: str
    title: str
    authors: list[str]
    arxiv_id: str
    summary: str
    tags: list[str]
    created_at: str

    @classmethod
    def create(cls, title: str, authors: list[str], arxiv_id: str = "",
               summary: str = "", tags: list[str] = None) -> "PaperEntry":
        return cls(
            id=str(uuid.uuid4()),
            title=title,
            authors=authors,
            arxiv_id=arxiv_id,
            summary=summary,
            tags=tags or [],
            created_at=datetime.now().isoformat(),
        )


@dataclass
class CitationEntry:
    id: str
    bibtex_key: str
    paper_id: Optional[str]
    reason: str
    created_at: str

    @classmethod
    def create(cls, bibtex_key: str, reason: str, paper_id: str = None) -> "CitationEntry":
        return cls(
            id=str(uuid.uuid4()),
            bibtex_key=bibtex_key,
            paper_id=paper_id,
            reason=reason,
            created_at=datetime.now().isoformat(),
        )


@dataclass
class ConventionEntry:
    id: str
    rule: str
    example: str
    created_at: str

    @classmethod
    def create(cls, rule: str, example: str = "") -> "ConventionEntry":
        return cls(
            id=str(uuid.uuid4()),
            rule=rule,
            example=example,
            created_at=datetime.now().isoformat(),
        )


@dataclass
class TodoEntry:
    id: str
    task: str
    priority: Literal["low", "medium", "high"]
    status: Literal["pending", "in_progress", "completed"]
    created_at: str

    @classmethod
    def create(cls, task: str, priority: str = "medium",
               status: str = "pending") -> "TodoEntry":
        return cls(
            id=str(uuid.uuid4()),
            task=task,
            priority=priority,
            status=status,
            created_at=datetime.now().isoformat(),
        )


@dataclass
class NoteEntry:
    id: str
    content: str
    tags: list[str]
    created_at: str

    @classmethod
    def create(cls, content: str, tags: list[str] = None) -> "NoteEntry":
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            tags=tags or [],
            created_at=datetime.now().isoformat(),
        )


@dataclass
class MemoryData:
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    papers: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    conventions: list[dict] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    # Literature verifier state (isolated from agent memory)
    literature_verifier: dict = field(default_factory=lambda: {
        "approved_citations": [],
        "last_run": None,
    })

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


class MemoryService:
    """
    Manages project memory stored in .aura/memory.json
    """

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.aura_dir = self.project_path / ".aura"
        self.memory_file = self.aura_dir / "memory.json"

    def _ensure_aura_dir(self) -> None:
        """Ensure .aura directory exists."""
        self.aura_dir.mkdir(exist_ok=True)

    def load(self) -> MemoryData:
        """Load memory from disk."""
        if not self.memory_file.exists():
            return MemoryData()

        try:
            data = json.loads(self.memory_file.read_text())
            return MemoryData(
                version=data.get("version", 1),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                papers=data.get("papers", []),
                citations=data.get("citations", []),
                conventions=data.get("conventions", []),
                todos=data.get("todos", []),
                notes=data.get("notes", []),
                literature_verifier=data.get("literature_verifier", {
                    "approved_citations": [],
                    "last_run": None,
                }),
            )
        except (json.JSONDecodeError, KeyError):
            return MemoryData()

    def save(self, memory: MemoryData) -> None:
        """Save memory to disk."""
        self._ensure_aura_dir()
        memory.updated_at = datetime.now().isoformat()
        self.memory_file.write_text(json.dumps(asdict(memory), indent=2))

    def add_entry(self, entry_type: EntryType, entry_data: dict) -> dict:
        """Add a new entry of the given type."""
        memory = self.load()
        entries = getattr(memory, entry_type)

        # Create entry with ID and timestamp
        entry = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
            **entry_data,
        }
        entries.append(entry)
        self.save(memory)
        return entry

    def update_entry(self, entry_type: EntryType, entry_id: str,
                     entry_data: dict) -> Optional[dict]:
        """Update an existing entry."""
        memory = self.load()
        entries = getattr(memory, entry_type)

        for i, entry in enumerate(entries):
            if entry.get("id") == entry_id:
                # Preserve id and created_at
                updated = {
                    **entry_data,
                    "id": entry_id,
                    "created_at": entry.get("created_at", datetime.now().isoformat()),
                }
                entries[i] = updated
                self.save(memory)
                return updated

        return None

    def delete_entry(self, entry_type: EntryType, entry_id: str) -> bool:
        """Delete an entry by ID."""
        memory = self.load()
        entries = getattr(memory, entry_type)

        for i, entry in enumerate(entries):
            if entry.get("id") == entry_id:
                entries.pop(i)
                self.save(memory)
                return True

        return False

    def estimate_tokens(self) -> int:
        """Estimate token count for all memory content."""
        memory = self.load()
        text = self.format_for_prompt(memory)
        return len(text) // CHARS_PER_TOKEN

    def get_stats(self) -> dict:
        """Get memory statistics."""
        token_count = self.estimate_tokens()
        return {
            "token_count": token_count,
            "warning": token_count > TOKEN_WARNING_THRESHOLD,
            "threshold": TOKEN_WARNING_THRESHOLD,
        }

    def format_for_prompt(self, memory: MemoryData = None) -> str:
        """Format memory for injection into system prompt."""
        if memory is None:
            memory = self.load()

        sections = []

        # Papers
        if memory.papers:
            lines = [f"### Papers ({len(memory.papers)} entries)"]
            for p in memory.papers:
                authors = ", ".join(p.get("authors", []))
                arxiv = f" [{p.get('arxiv_id')}]" if p.get("arxiv_id") else ""
                lines.append(f"- **{p.get('title')}** ({authors}){arxiv}")
                if p.get("summary"):
                    lines.append(f"  Summary: {p.get('summary')}")
                if p.get("tags"):
                    lines.append(f"  Tags: {', '.join(p.get('tags'))}")
            sections.append("\n".join(lines))

        # Citations
        if memory.citations:
            lines = [f"### Citations ({len(memory.citations)} entries)"]
            for c in memory.citations:
                lines.append(f"- `{c.get('bibtex_key')}` → {c.get('reason')}")
            sections.append("\n".join(lines))

        # Conventions
        if memory.conventions:
            lines = [f"### Conventions ({len(memory.conventions)} entries)"]
            for c in memory.conventions:
                example = f" (e.g., \"{c.get('example')}\")" if c.get("example") else ""
                lines.append(f"- {c.get('rule')}{example}")
            sections.append("\n".join(lines))

        # Todos
        if memory.todos:
            lines = [f"### Todos ({len(memory.todos)} entries)"]
            for t in memory.todos:
                priority = t.get("priority", "medium").upper()
                status = t.get("status", "pending")
                lines.append(f"- [{priority}] {t.get('task')} ({status})")
            sections.append("\n".join(lines))

        # Notes
        if memory.notes:
            lines = [f"### Notes ({len(memory.notes)} entries)"]
            for n in memory.notes:
                tags = " " + " ".join(f"#{t}" for t in n.get("tags", [])) if n.get("tags") else ""
                lines.append(f"- {n.get('content')}{tags}")
            sections.append("\n".join(lines))

        if not sections:
            return ""

        return "## Project Memory\n\n" + "\n\n".join(sections)

    def get_approved_citations(self) -> list[str]:
        """Get list of manually approved citation keys."""
        memory = self.load()
        return memory.literature_verifier.get("approved_citations", [])

    def approve_citation(self, cite_key: str) -> None:
        """Mark a citation as manually approved."""
        memory = self.load()
        approved = memory.literature_verifier.get("approved_citations", [])
        if cite_key not in approved:
            approved.append(cite_key)
            memory.literature_verifier["approved_citations"] = approved
            memory.literature_verifier["last_run"] = datetime.now().isoformat()
            self.save(memory)

    def unapprove_citation(self, cite_key: str) -> None:
        """Remove manual approval from a citation."""
        memory = self.load()
        approved = memory.literature_verifier.get("approved_citations", [])
        if cite_key in approved:
            approved.remove(cite_key)
            memory.literature_verifier["approved_citations"] = approved
            self.save(memory)
