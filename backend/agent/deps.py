"""
Agent Dependencies

Shared dependencies dataclass used by the agent and tools.
Separated to avoid circular imports.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.hitl import HITLManager
    from agent.hitl_store import HITLStore
    from agent.hitl_ws import HITLWebSocketManager
    from agent.planning import PlanManager


@dataclass
class AuraDeps:
    """
    Dependencies injected into agent tools.

    These are passed to every tool call via RunContext.
    """
    project_path: str
    project_name: str = ""

    # HITL support - blocking mode (legacy, for backward compatibility)
    hitl_manager: Optional["HITLManager"] = None

    # HITL support - async mode (new non-blocking)
    hitl_store: Optional["HITLStore"] = None
    hitl_ws: Optional["HITLWebSocketManager"] = None

    # Planning support (optional)
    plan_manager: Optional["PlanManager"] = None
    session_id: str = "default"

    # Provider info (for prompt adjustments)
    provider_name: str = "openrouter"

    # HITL mode: "blocking" (legacy) or "async" (new non-blocking)
    hitl_mode: str = "blocking"

    def __post_init__(self):
        if not self.project_name and self.project_path:
            self.project_name = Path(self.project_path).name
