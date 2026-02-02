"""
Agent Context

Holds the context for agent execution, including project information
and conversation history.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


@dataclass
class AgentContext:
    """
    Context for agent execution.

    Contains all information the agent needs to operate on a project.
    """

    # Project information
    project_path: str
    project_name: str = ""

    # Current state
    current_file: Optional[str] = None

    # Conversation history (Anthropic message format)
    history: list[dict] = field(default_factory=list)

    # Session metadata
    session_id: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.project_name and self.project_path:
            from pathlib import Path
            self.project_name = Path(self.project_path).name

        if not self.session_id:
            import uuid
            self.session_id = str(uuid.uuid4())[:8]

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.history.append({
            "role": "user",
            "content": content,
        })

    def add_assistant_message(self, content: str | list):
        """Add an assistant message to history."""
        self.history.append({
            "role": "assistant",
            "content": content,
        })

    def get_messages(self) -> list[dict]:
        """Get conversation history in Anthropic format."""
        return self.history.copy()

    def clear_history(self):
        """Clear conversation history."""
        self.history = []

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "project_path": self.project_path,
            "project_name": self.project_name,
            "current_file": self.current_file,
            "history": self.history,
            "session_id": self.session_id,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentContext":
        """Create from dictionary."""
        return cls(
            project_path=data["project_path"],
            project_name=data.get("project_name", ""),
            current_file=data.get("current_file"),
            history=data.get("history", []),
            session_id=data.get("session_id", ""),
            started_at=data.get("started_at", ""),
        )
