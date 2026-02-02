"""
Planning System for Aura Agent

Provides structured planning capabilities for complex tasks.
Plans are created by the PlannerAgent and tracked during execution.

Architecture:
    1. User requests a complex task
    2. Main agent detects complexity and invokes PlannerAgent
    3. PlannerAgent analyzes task and creates structured Plan
    4. Main agent executes plan step-by-step
    5. Plan state is tracked and updated throughout execution
    6. User can see plan progress via streaming events

Key Components:
    - Plan: Structured representation of a multi-step task
    - PlanStep: Individual step with status tracking
    - PlanManager: Manages plan lifecycle and state
    - PlanningConfig: Configuration for planning behavior
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PlanningConfig:
    """Configuration for planning behavior."""

    # Minimum task complexity to trigger auto-planning
    # Complexity is estimated by: number of files, steps mentioned, etc.
    auto_plan_threshold: int = 3

    # Maximum steps in a plan
    max_plan_steps: int = 20

    # Whether to require user approval before executing plan
    require_approval: bool = False

    # Timeout for plan creation (seconds)
    creation_timeout: float = 60.0

    # Keywords that trigger planning
    trigger_keywords: set[str] = field(default_factory=lambda: {
        "implement", "create", "build", "refactor", "migrate",
        "add feature", "set up", "configure", "redesign", "rewrite",
        "multiple files", "several", "steps", "comprehensive",
    })


# =============================================================================
# Plan Data Structures
# =============================================================================

class PlanStatus(str, Enum):
    """Status of a plan."""
    DRAFT = "draft"           # Plan created but not approved
    APPROVED = "approved"     # Plan approved, ready to execute
    IN_PROGRESS = "in_progress"  # Execution started
    COMPLETED = "completed"   # All steps done
    FAILED = "failed"         # Execution failed
    CANCELLED = "cancelled"   # User cancelled


class StepStatus(str, Enum):
    """Status of a plan step."""
    PENDING = "pending"       # Not started
    IN_PROGRESS = "in_progress"  # Currently executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Failed to execute
    SKIPPED = "skipped"       # Skipped (dependency failed or user choice)


class StepType(str, Enum):
    """Type of plan step."""
    ANALYSIS = "analysis"     # Reading/understanding code
    EDIT = "edit"             # Modifying files
    CREATE = "create"         # Creating new files
    DELETE = "delete"         # Removing files
    COMPILE = "compile"       # Compilation/build
    TEST = "test"             # Running tests
    RESEARCH = "research"     # Research/lookup
    VERIFY = "verify"         # Verification step
    OTHER = "other"           # Other actions


@dataclass
class PlanStep:
    """
    A single step in a plan.

    Steps are executed in order, respecting dependencies.
    Each step tracks its own status and any output/errors.
    """
    # Identity
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_number: int = 0

    # Content
    title: str = ""
    description: str = ""
    step_type: StepType = StepType.OTHER

    # Files involved
    files: list[str] = field(default_factory=list)

    # Dependencies (step_ids that must complete first)
    depends_on: list[str] = field(default_factory=list)

    # Status tracking
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Execution results
    output: str = ""
    error: str | None = None

    # Verification criteria
    verification: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "title": self.title,
            "description": self.description,
            "step_type": self.step_type.value,
            "files": self.files,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output": self.output,
            "error": self.error,
            "verification": self.verification,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        """Create from dictionary."""
        step = cls(
            step_id=data.get("step_id", str(uuid.uuid4())[:8]),
            step_number=data.get("step_number", 0),
            title=data.get("title", ""),
            description=data.get("description", ""),
            step_type=StepType(data.get("step_type", "other")),
            files=data.get("files", []),
            depends_on=data.get("depends_on", []),
            status=StepStatus(data.get("status", "pending")),
            verification=data.get("verification", ""),
        )
        return step

    def mark_started(self):
        """Mark step as started."""
        self.status = StepStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, output: str = ""):
        """Mark step as completed."""
        self.status = StepStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.output = output

    def mark_failed(self, error: str):
        """Mark step as failed."""
        self.status = StepStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error = error

    def mark_skipped(self, reason: str = ""):
        """Mark step as skipped."""
        self.status = StepStatus.SKIPPED
        self.output = reason


@dataclass
class Plan:
    """
    A structured plan for executing a complex task.

    Plans contain:
    - Goal: What we're trying to achieve
    - Steps: Ordered list of actions
    - Context: Background information
    - Risks: Potential issues
    """
    # Identity
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Task information
    goal: str = ""
    original_request: str = ""
    context: str = ""

    # Steps
    steps: list[PlanStep] = field(default_factory=list)

    # Metadata
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Analysis
    complexity: int = 1  # 1-5 scale
    estimated_files: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    # Execution tracking
    current_step_index: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "original_request": self.original_request,
            "context": self.context,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "complexity": self.complexity,
            "estimated_files": self.estimated_files,
            "risks": self.risks,
            "assumptions": self.assumptions,
            "current_step_index": self.current_step_index,
            "progress": self.progress,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        """Create from dictionary."""
        plan = cls(
            plan_id=data.get("plan_id", str(uuid.uuid4())),
            goal=data.get("goal", ""),
            original_request=data.get("original_request", ""),
            context=data.get("context", ""),
            status=PlanStatus(data.get("status", "draft")),
            complexity=data.get("complexity", 1),
            estimated_files=data.get("estimated_files", []),
            risks=data.get("risks", []),
            assumptions=data.get("assumptions", []),
            current_step_index=data.get("current_step_index", 0),
        )
        plan.steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return plan

    @property
    def progress(self) -> dict:
        """Get progress statistics."""
        total = len(self.steps)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "percent": 0}

        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        skipped = sum(1 for s in self.steps if s.status == StepStatus.SKIPPED)
        in_progress = sum(1 for s in self.steps if s.status == StepStatus.IN_PROGRESS)
        pending = sum(1 for s in self.steps if s.status == StepStatus.PENDING)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "in_progress": in_progress,
            "pending": pending,
            "percent": int((completed + skipped) / total * 100),
        }

    @property
    def current_step(self) -> PlanStep | None:
        """Get the current step being executed."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def next_pending_step(self) -> PlanStep | None:
        """Get the next pending step."""
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                # Check dependencies
                deps_met = all(
                    self.get_step(dep_id) and self.get_step(dep_id).status in [StepStatus.COMPLETED, StepStatus.SKIPPED]
                    for dep_id in step.depends_on
                )
                if deps_met:
                    return step
        return None

    def get_step(self, step_id: str) -> PlanStep | None:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def add_step(self, step: PlanStep):
        """Add a step to the plan."""
        step.step_number = len(self.steps) + 1
        self.steps.append(step)
        self.updated_at = datetime.now(timezone.utc)

    def update_step_status(self, step_id: str, status: StepStatus, output: str = "", error: str | None = None):
        """Update a step's status."""
        step = self.get_step(step_id)
        if step:
            step.status = status
            if output:
                step.output = output
            if error:
                step.error = error
            if status == StepStatus.IN_PROGRESS:
                step.started_at = datetime.now(timezone.utc)
            elif status in [StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED]:
                step.completed_at = datetime.now(timezone.utc)
            self.updated_at = datetime.now(timezone.utc)

            # Update plan status
            self._update_plan_status()

    def _update_plan_status(self):
        """Update overall plan status based on step statuses."""
        if not self.steps:
            return

        all_completed = all(s.status in [StepStatus.COMPLETED, StepStatus.SKIPPED] for s in self.steps)
        any_failed = any(s.status == StepStatus.FAILED for s in self.steps)
        any_in_progress = any(s.status == StepStatus.IN_PROGRESS for s in self.steps)

        if all_completed:
            self.status = PlanStatus.COMPLETED
        elif any_failed:
            self.status = PlanStatus.FAILED
        elif any_in_progress or self.status == PlanStatus.APPROVED:
            self.status = PlanStatus.IN_PROGRESS

    def to_markdown(self) -> str:
        """Convert plan to markdown for display."""
        lines = [
            f"# Plan: {self.goal}",
            "",
            f"**Status:** {self.status.value}",
            f"**Complexity:** {self.complexity}/5",
            f"**Progress:** {self.progress['percent']}% ({self.progress['completed']}/{self.progress['total']} steps)",
            "",
        ]

        if self.context:
            lines.extend(["## Context", self.context, ""])

        if self.risks:
            lines.extend(["## Risks", *[f"- {r}" for r in self.risks], ""])

        lines.append("## Steps")
        lines.append("")

        for step in self.steps:
            status_icon = {
                StepStatus.PENDING: "⬜",
                StepStatus.IN_PROGRESS: "🔄",
                StepStatus.COMPLETED: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️",
            }.get(step.status, "⬜")

            lines.append(f"{status_icon} **Step {step.step_number}: {step.title}**")
            if step.description:
                lines.append(f"   {step.description}")
            if step.files:
                lines.append(f"   Files: {', '.join(step.files)}")
            if step.error:
                lines.append(f"   ❌ Error: {step.error}")
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# Plan Manager
# =============================================================================

class PlanManager:
    """
    Manages plan lifecycle and execution state.

    Features:
    - Create and store plans
    - Track execution progress
    - Emit events for streaming
    - Support multiple concurrent plans (per session)
    """

    def __init__(self, config: PlanningConfig | None = None):
        self.config = config or PlanningConfig()

        # Active plans by session_id
        self._plans: dict[str, Plan] = {}

        # Completed/cancelled plan history by session_id
        self._history: dict[str, list[Plan]] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Event callbacks
        self._on_plan_created: Callable | None = None
        self._on_step_started: Callable | None = None
        self._on_step_completed: Callable | None = None
        self._on_plan_completed: Callable | None = None

    def set_callbacks(
        self,
        on_plan_created: Callable | None = None,
        on_step_started: Callable | None = None,
        on_step_completed: Callable | None = None,
        on_plan_completed: Callable | None = None,
    ):
        """Set event callbacks."""
        self._on_plan_created = on_plan_created
        self._on_step_started = on_step_started
        self._on_step_completed = on_step_completed
        self._on_plan_completed = on_plan_completed

    async def create_plan(
        self,
        goal: str,
        original_request: str,
        steps: list[dict],
        session_id: str = "default",
        **kwargs,
    ) -> Plan:
        """
        Create a new plan.

        Args:
            goal: What the plan aims to achieve
            original_request: The user's original request
            steps: List of step dictionaries
            session_id: Session identifier
            **kwargs: Additional plan attributes

        Returns:
            Created Plan object
        """
        async with self._lock:
            plan = Plan(
                goal=goal,
                original_request=original_request,
                context=kwargs.get("context", ""),
                complexity=kwargs.get("complexity", len(steps)),
                estimated_files=kwargs.get("estimated_files", []),
                risks=kwargs.get("risks", []),
                assumptions=kwargs.get("assumptions", []),
            )

            # Add steps
            for i, step_data in enumerate(steps):
                step = PlanStep(
                    step_number=i + 1,
                    title=step_data.get("title", f"Step {i + 1}"),
                    description=step_data.get("description", ""),
                    step_type=StepType(step_data.get("type", "other")),
                    files=step_data.get("files", []),
                    depends_on=step_data.get("depends_on", []),
                    verification=step_data.get("verification", ""),
                )
                plan.steps.append(step)

            self._plans[session_id] = plan

            logger.info(f"Created plan '{plan.plan_id}' with {len(plan.steps)} steps")

            if self._on_plan_created:
                await self._on_plan_created(plan)

            return plan

    async def get_plan(self, session_id: str = "default") -> Plan | None:
        """Get the active plan for a session."""
        return self._plans.get(session_id)

    async def update_step(
        self,
        step_id: str,
        status: StepStatus,
        output: str = "",
        error: str | None = None,
        session_id: str = "default",
    ) -> bool:
        """
        Update a step's status.

        Args:
            step_id: ID of the step to update
            status: New status
            output: Output from execution
            error: Error message if failed
            session_id: Session identifier

        Returns:
            True if updated, False if step not found
        """
        async with self._lock:
            plan = self._plans.get(session_id)
            if not plan:
                return False

            step = plan.get_step(step_id)
            if not step:
                return False

            old_status = step.status
            plan.update_step_status(step_id, status, output, error)

            # Emit events
            if status == StepStatus.IN_PROGRESS and self._on_step_started:
                await self._on_step_started(plan, step)
            elif status in [StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED]:
                if self._on_step_completed:
                    await self._on_step_completed(plan, step)
                if plan.status in [PlanStatus.COMPLETED, PlanStatus.FAILED]:
                    plan.completed_at = datetime.now(timezone.utc)
                    if self._on_plan_completed:
                        await self._on_plan_completed(plan)
                    # Archive completed/failed plans to history
                    self._archive_plan(session_id, plan)

            logger.info(f"Step '{step.title}' status: {old_status.value} -> {status.value}")
            return True

    async def start_next_step(self, session_id: str = "default") -> PlanStep | None:
        """
        Get and start the next pending step.

        Returns:
            The step that was started, or None if no steps available
        """
        async with self._lock:
            plan = self._plans.get(session_id)
            if not plan:
                return None

            step = plan.next_pending_step
            if step:
                step.mark_started()
                plan.current_step_index = step.step_number - 1

                if self._on_step_started:
                    await self._on_step_started(plan, step)

            return step

    async def complete_current_step(
        self,
        output: str = "",
        session_id: str = "default",
    ) -> bool:
        """Complete the current in-progress step."""
        plan = self._plans.get(session_id)
        if not plan or not plan.current_step:
            return False

        step = plan.current_step
        if step.status != StepStatus.IN_PROGRESS:
            return False

        return await self.update_step(
            step.step_id, StepStatus.COMPLETED, output, session_id=session_id
        )

    async def fail_current_step(
        self,
        error: str,
        session_id: str = "default",
    ) -> bool:
        """Mark the current step as failed."""
        plan = self._plans.get(session_id)
        if not plan or not plan.current_step:
            return False

        step = plan.current_step
        return await self.update_step(
            step.step_id, StepStatus.FAILED, error=error, session_id=session_id
        )

    async def approve_plan(self, session_id: str = "default") -> bool:
        """Approve a plan for execution."""
        async with self._lock:
            plan = self._plans.get(session_id)
            if not plan or plan.status != PlanStatus.DRAFT:
                return False

            plan.status = PlanStatus.APPROVED
            plan.updated_at = datetime.now(timezone.utc)
            return True

    async def cancel_plan(self, session_id: str = "default") -> bool:
        """Cancel a plan."""
        async with self._lock:
            plan = self._plans.get(session_id)
            if not plan:
                return False

            plan.status = PlanStatus.CANCELLED
            plan.updated_at = datetime.now(timezone.utc)
            plan.completed_at = datetime.now(timezone.utc)

            # Archive to history
            self._archive_plan(session_id, plan)
            return True

    def _archive_plan(self, session_id: str, plan: Plan):
        """Move a plan to history."""
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append(plan)
        # Keep only last 20 plans per session
        if len(self._history[session_id]) > 20:
            self._history[session_id] = self._history[session_id][-20:]
        # Remove from active
        if session_id in self._plans:
            del self._plans[session_id]

    async def get_history(self, session_id: str = "default", limit: int = 10) -> list[Plan]:
        """
        Get plan history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of plans to return

        Returns:
            List of completed/cancelled plans (most recent first)
        """
        history = self._history.get(session_id, [])
        return list(reversed(history[-limit:]))

    async def clear_plan(self, session_id: str = "default"):
        """Remove a plan from the manager."""
        async with self._lock:
            if session_id in self._plans:
                del self._plans[session_id]

    def should_create_plan(self, request: str) -> bool:
        """
        Determine if a request should trigger plan creation.

        Args:
            request: User's request text

        Returns:
            True if planning is recommended
        """
        request_lower = request.lower()

        # Check for trigger keywords
        for keyword in self.config.trigger_keywords:
            if keyword in request_lower:
                return True

        # Check for complexity indicators
        complexity_indicators = [
            "multiple", "several", "all", "each", "every",
            "step by step", "steps", "phases", "stages",
            "first", "then", "after that", "finally",
        ]
        indicator_count = sum(1 for ind in complexity_indicators if ind in request_lower)

        return indicator_count >= self.config.auto_plan_threshold


# =============================================================================
# Singleton Manager
# =============================================================================

_default_manager: PlanManager | None = None


def get_plan_manager() -> PlanManager:
    """Get or create the default plan manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = PlanManager()
    return _default_manager


def reset_plan_manager():
    """Reset the plan manager (useful for testing)."""
    global _default_manager
    _default_manager = None
