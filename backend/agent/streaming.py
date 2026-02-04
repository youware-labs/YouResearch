"""
Streaming Runner for PydanticAI Agent

Provides SSE (Server-Sent Events) streaming for the Aura agent.
Streams text deltas and tool events to the frontend.

Features:
- Text streaming with deltas
- Tool call and result events
- Automatic message compression for long conversations
- Human-in-the-loop (HITL) approval for dangerous operations
- Steering messages for mid-conversation guidance
"""

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Optional
from datetime import datetime
from pathlib import Path
import json
import logging
import uuid

from pydantic_ai.agent import ModelRequestNode, CallToolsNode, UserPromptNode
from pydantic_ai.run import End
from pydantic_ai.messages import ToolCallPart, TextPart, ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai import UsageLimits

from agent.pydantic_agent import aura_agent, AuraDeps
from agent.compression import compress_if_needed, get_compressor

logger = logging.getLogger(__name__)


# =============================================================================
# Session-based History Storage
# =============================================================================

# Store actual PydanticAI messages per session (in-memory for now)
# Key: session_id, Value: list of ModelRequest/ModelResponse
_session_histories: dict[str, list] = {}


def get_session_history(session_id: str) -> list:
    """Get message history for a session."""
    return _session_histories.get(session_id, [])


def save_session_history(session_id: str, messages: list) -> None:
    """Save message history for a session."""
    _session_histories[session_id] = messages


def clear_session_history(session_id: str) -> None:
    """Clear message history for a session."""
    if session_id in _session_histories:
        del _session_histories[session_id]


# =============================================================================
# ChatSession - Persistent Chat Sessions
# =============================================================================

@dataclass
class ChatSession:
    """
    Represents a persistent chat session stored in {projectPath}/.aura/chat_session_{id}.json.

    Each session stores the full PydanticAI message history for conversation continuity.
    Also stores active execution plan and plan history.
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    name: str = ""
    project_path: str = ""
    messages: list[dict] = field(default_factory=list)
    updated_at: str = ""
    message_count: int = 0
    active_plan: dict | None = None  # Currently executing plan
    plan_history: list[dict] = field(default_factory=list)  # Completed/cancelled plans

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.name:
            self.name = f"Chat {self.session_id}"

    def set_messages(self, pydantic_messages: list) -> None:
        """
        Serialize PydanticAI messages to storable dicts.

        Converts ModelRequest/ModelResponse to JSON-serializable format.
        """
        serialized = []
        for msg in pydantic_messages:
            if isinstance(msg, ModelRequest):
                parts_data = []
                for part in msg.parts:
                    if isinstance(part, UserPromptPart):
                        parts_data.append({
                            "type": "user_prompt",
                            "content": part.content,
                            "timestamp": part.timestamp.isoformat() if part.timestamp else None,
                        })
                    elif hasattr(part, "to_dict"):
                        parts_data.append(part.to_dict())
                    else:
                        # Tool return parts etc
                        parts_data.append({
                            "type": part.__class__.__name__,
                            "data": str(part),
                        })
                serialized.append({
                    "type": "ModelRequest",
                    "parts": parts_data,
                })
            elif isinstance(msg, ModelResponse):
                parts_data = []
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        parts_data.append({
                            "type": "text",
                            "content": part.content,
                        })
                    elif isinstance(part, ToolCallPart):
                        try:
                            args = part.args_as_dict()
                        except Exception as e:
                            logger.error(f"Failed to serialize tool call args: {e}")
                            args = {"_parse_error": str(e)}
                        parts_data.append({
                            "type": "tool_call",
                            "tool_name": part.tool_name,
                            "tool_call_id": part.tool_call_id,
                            "args": args,
                        })
                    elif hasattr(part, "to_dict"):
                        parts_data.append(part.to_dict())
                    else:
                        parts_data.append({
                            "type": part.__class__.__name__,
                            "data": str(part),
                        })
                serialized.append({
                    "type": "ModelResponse",
                    "parts": parts_data,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "model_name": getattr(msg, "model_name", None),
                })
            else:
                # Fallback for unknown types
                serialized.append({
                    "type": msg.__class__.__name__,
                    "data": str(msg),
                })

        self.messages = serialized
        self.message_count = len(serialized)
        self.updated_at = datetime.now().isoformat()

    def get_pydantic_messages(self) -> list:
        """
        Reconstruct PydanticAI messages from stored dicts.
        """
        from datetime import timezone

        reconstructed = []
        for msg in self.messages:
            msg_type = msg.get("type", "")

            if msg_type == "ModelRequest":
                parts = []
                for part_data in msg.get("parts", []):
                    part_type = part_data.get("type", "")
                    if part_type == "user_prompt":
                        ts = part_data.get("timestamp")
                        timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
                        parts.append(UserPromptPart(
                            content=part_data.get("content", ""),
                            timestamp=timestamp,
                        ))
                    # Skip other part types for now (tool return parts etc.)

                if parts:
                    reconstructed.append(ModelRequest(parts=parts))

            elif msg_type == "ModelResponse":
                parts = []
                for part_data in msg.get("parts", []):
                    part_type = part_data.get("type", "")
                    if part_type == "text":
                        parts.append(TextPart(content=part_data.get("content", "")))
                    # Skip tool calls for now - they're already executed

                if parts:
                    ts = msg.get("timestamp")
                    timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
                    reconstructed.append(ModelResponse(
                        parts=parts,
                        timestamp=timestamp,
                        model_name=msg.get("model_name", "history"),
                    ))

        # Ensure proper alternation
        if reconstructed and isinstance(reconstructed[-1], ModelResponse):
            reconstructed = reconstructed[:-1]

        return reconstructed

    def save(self) -> None:
        """Save session to disk at {project_path}/.aura/chat_session_{id}.json"""
        if not self.project_path:
            raise ValueError("project_path is required to save session")

        aura_dir = Path(self.project_path) / ".aura"
        aura_dir.mkdir(parents=True, exist_ok=True)

        session_file = aura_dir / f"chat_session_{self.session_id}.json"

        data = {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "name": self.name,
            "message_count": self.message_count,
            "messages": self.messages,
            "active_plan": self.active_plan,
            "plan_history": self.plan_history,
        }

        session_file.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved chat session {self.session_id} with {self.message_count} messages")

    @classmethod
    def load(cls, project_path: str, session_id: str) -> Optional["ChatSession"]:
        """Load a session from disk."""
        session_file = Path(project_path) / ".aura" / f"chat_session_{session_id}.json"

        if not session_file.exists():
            return None

        try:
            data = json.loads(session_file.read_text())
            session = cls(
                session_id=data.get("session_id", session_id),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                name=data.get("name", ""),
                project_path=project_path,
                messages=data.get("messages", []),
                message_count=data.get("message_count", 0),
                active_plan=data.get("active_plan"),  # None if not present (backward compat)
                plan_history=data.get("plan_history", []),  # Empty list if not present
            )
            return session
        except Exception as e:
            logger.error(f"Failed to load chat session {session_id}: {e}")
            return None

    @classmethod
    def list_sessions(cls, project_path: str) -> list[dict]:
        """List all chat sessions for a project (sorted by updated_at, newest first)."""
        aura_dir = Path(project_path) / ".aura"
        if not aura_dir.exists():
            return []

        sessions = []
        for session_file in aura_dir.glob("chat_session_*.json"):
            try:
                data = json.loads(session_file.read_text())
                sessions.append({
                    "session_id": data.get("session_id", ""),
                    "name": data.get("name", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": data.get("message_count", 0),
                })
            except Exception as e:
                logger.warning(f"Failed to read session file {session_file}: {e}")

        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    @classmethod
    def delete(cls, project_path: str, session_id: str) -> bool:
        """Delete a session file."""
        session_file = Path(project_path) / ".aura" / f"chat_session_{session_id}.json"

        if not session_file.exists():
            return False

        try:
            session_file.unlink()
            # Also clear from in-memory cache
            if session_id in _session_histories:
                del _session_histories[session_id]
            logger.info(f"Deleted chat session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete chat session {session_id}: {e}")
            return False

    def to_summary(self) -> dict:
        """Return a summary dict (without full messages)."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
        }

    def set_active_plan(self, plan_dict: dict | None) -> None:
        """Set the active plan for this session."""
        self.active_plan = plan_dict
        self.updated_at = datetime.now().isoformat()

    def archive_plan(self) -> None:
        """Move active plan to history and clear it."""
        if self.active_plan:
            self.plan_history.append(self.active_plan)
            # Keep only last 10 plans in history
            if len(self.plan_history) > 10:
                self.plan_history = self.plan_history[-10:]
            self.active_plan = None
            self.updated_at = datetime.now().isoformat()


def get_session_history_from_disk(project_path: str, session_id: str) -> list:
    """
    Get session history, loading from disk if not in memory.
    """
    # Check in-memory cache first
    if session_id in _session_histories:
        return _session_histories[session_id]

    # Try loading from disk
    session = ChatSession.load(project_path, session_id)
    if session:
        messages = session.get_pydantic_messages()
        _session_histories[session_id] = messages
        return messages

    return []


def save_session_history_to_disk(project_path: str, session_id: str, messages: list, session_name: str = "") -> None:
    """
    Save session history to both memory and disk.
    """
    # Save to in-memory cache
    _session_histories[session_id] = messages

    # Load or create session
    session = ChatSession.load(project_path, session_id)
    if not session:
        session = ChatSession(
            session_id=session_id,
            project_path=project_path,
            name=session_name or f"Chat {session_id}",
        )
    else:
        session.project_path = project_path

    # Update messages and save
    session.set_messages(messages)
    session.save()


def convert_simple_history(history: list) -> list:
    """
    Convert simple history format to PydanticAI message format.

    Input format: [{"role": "user"|"assistant", "content": "..."}]
    Output format: [ModelRequest(...), ModelResponse(...), ...]

    PydanticAI requires alternating ModelRequest/ModelResponse pairs.
    """
    if not history:
        return []

    # Check if already in PydanticAI format
    if history and isinstance(history[0], (ModelRequest, ModelResponse)):
        return history

    converted = []
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for msg in history:
        if not isinstance(msg, dict):
            continue

        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            converted.append(ModelRequest(
                parts=[UserPromptPart(content=content, timestamp=now)],
            ))
        elif role == "assistant":
            converted.append(ModelResponse(
                parts=[TextPart(content=content)],
                timestamp=now,
                model_name="history",
            ))

    # PydanticAI requires history to end with ModelRequest (user message)
    # If history ends with assistant message, we need to handle that
    # The simplest approach: don't pass history that ends with assistant
    if converted and isinstance(converted[-1], ModelResponse):
        # Remove trailing assistant message - the agent will regenerate
        converted = converted[:-1]

    return converted


# =============================================================================
# Stream Event Types
# =============================================================================

@dataclass
class StreamEvent:
    """Base class for stream events sent via SSE."""
    type: str

    def to_sse(self) -> str:
        """Convert to SSE format."""
        return f"data: {json.dumps(self.to_dict())}\n\n"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        raise NotImplementedError


@dataclass
class TextDeltaEvent(StreamEvent):
    """Text chunk from the model."""
    type: Literal["text_delta"] = "text_delta"
    content: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "content": self.content}


@dataclass
class ToolCallEvent(StreamEvent):
    """Tool is being called."""
    type: Literal["tool_call"] = "tool_call"
    tool_name: str = ""
    tool_call_id: str = ""
    args: dict = None

    def __post_init__(self):
        if self.args is None:
            self.args = {}

    def to_dict(self) -> dict:
        return {"type": self.type, "tool_name": self.tool_name, "tool_call_id": self.tool_call_id, "args": self.args}


@dataclass
class ToolResultEvent(StreamEvent):
    """Tool execution result."""
    type: Literal["tool_result"] = "tool_result"
    tool_name: str = ""
    tool_call_id: str = ""
    result: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "tool_name": self.tool_name, "tool_call_id": self.tool_call_id, "result": self.result}


@dataclass
class DoneEvent(StreamEvent):
    """Stream is complete."""
    type: Literal["done"] = "done"
    output: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "output": self.output,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            }
        }


@dataclass
class ErrorEvent(StreamEvent):
    """Error occurred during streaming."""
    type: Literal["error"] = "error"
    message: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "message": self.message}


@dataclass
class CompressionEvent(StreamEvent):
    """History was compressed to save context space."""
    type: Literal["compression"] = "compression"
    original_messages: int = 0
    compressed_messages: int = 0
    estimated_tokens_before: int = 0
    estimated_tokens_after: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "original_messages": self.original_messages,
            "compressed_messages": self.compressed_messages,
            "tokens_saved": self.estimated_tokens_before - self.estimated_tokens_after,
        }


@dataclass
class ApprovalRequiredEvent(StreamEvent):
    """Tool requires user approval before execution."""
    type: Literal["approval_required"] = "approval_required"
    request_id: str = ""
    tool_name: str = ""
    tool_args: dict = None

    def __post_init__(self):
        if self.tool_args is None:
            self.tool_args = {}

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
        }


@dataclass
class ApprovalResolvedEvent(StreamEvent):
    """Tool approval was resolved (approved/rejected)."""
    type: Literal["approval_resolved"] = "approval_resolved"
    request_id: str = ""
    status: str = ""  # "approved", "rejected", "modified", "timeout"
    tool_name: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "status": self.status,
            "tool_name": self.tool_name,
        }


@dataclass
class SteeringEvent(StreamEvent):
    """Steering message was injected into the conversation."""
    type: Literal["steering"] = "steering"
    messages_count: int = 0
    content_preview: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "messages_count": self.messages_count,
            "content_preview": self.content_preview,
        }


@dataclass
class PlanCreatedEvent(StreamEvent):
    """A plan was created for the task."""
    type: Literal["plan_created"] = "plan_created"
    plan_id: str = ""
    goal: str = ""
    steps_count: int = 0
    complexity: int = 1
    steps: list = None  # List of step dicts with step_number, title, description, status

    def __post_init__(self):
        if self.steps is None:
            self.steps = []

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps_count": self.steps_count,
            "complexity": self.complexity,
            "steps": self.steps,
        }


@dataclass
class PlanStepEvent(StreamEvent):
    """A plan step status changed."""
    type: Literal["plan_step"] = "plan_step"
    plan_id: str = ""
    step_number: int = 0
    step_title: str = ""
    status: str = ""  # "started", "completed", "failed", "skipped"
    progress_percent: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "plan_id": self.plan_id,
            "step_number": self.step_number,
            "step_title": self.step_title,
            "status": self.status,
            "progress_percent": self.progress_percent,
        }


@dataclass
class PlanCompletedEvent(StreamEvent):
    """A plan was completed."""
    type: Literal["plan_completed"] = "plan_completed"
    plan_id: str = ""
    goal: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "plan_id": self.plan_id,
            "goal": self.goal,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
        }


@dataclass
class DomainPreferenceRequestEvent(StreamEvent):
    """Research agent requests user's domain/field preference."""
    type: Literal["domain_preference_request"] = "domain_preference_request"
    request_id: str = ""
    topic: str = ""  # The research topic
    suggested_domain: str = ""  # LLM-suggested domain

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "topic": self.topic,
            "suggested_domain": self.suggested_domain,
        }


@dataclass
class VenuePreferenceRequestEvent(StreamEvent):
    """Research agent requests user's venue/conference preferences."""
    type: Literal["venue_preference_request"] = "venue_preference_request"
    request_id: str = ""
    topic: str = ""  # The research topic being searched
    domain: str = ""  # The selected domain
    suggested_venues: list = None  # LLM-suggested venues for the domain

    def __post_init__(self):
        if self.suggested_venues is None:
            self.suggested_venues = []

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "topic": self.topic,
            "domain": self.domain,
            "suggested_venues": self.suggested_venues,
        }


@dataclass
class VenuePreferenceResolvedEvent(StreamEvent):
    """Venue preference was submitted by user."""
    type: Literal["venue_preference_resolved"] = "venue_preference_resolved"
    request_id: str = ""
    venues: list = None

    def __post_init__(self):
        if self.venues is None:
            self.venues = []

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "request_id": self.request_id,
            "venues": self.venues,
        }


# =============================================================================
# Streaming Runner
# =============================================================================

async def stream_agent_response(
    message: str,
    project_path: str,
    project_name: str = "",
    message_history: list = None,
    auto_compress: bool = True,
    enable_hitl: bool = True,  # Enabled by default for file safety
    enable_steering: bool = False,
    enable_planning: bool = True,
    session_id: str | None = None,
    provider_config: dict | None = None,
) -> AsyncIterator[StreamEvent]:
    """
    Stream agent response as events.

    This is the main entry point for streaming agent interactions.
    It yields events that can be converted to SSE format.

    Args:
        message: User's message
        project_path: Path to the LaTeX project
        project_name: Optional project name (derived from path if not given)
        message_history: Optional conversation history for context
        auto_compress: Whether to automatically compress long histories (default: True)
        enable_hitl: Whether to enable human-in-the-loop approval (default: True)
        enable_steering: Whether to check for steering messages (default: False)
        session_id: Session ID for steering isolation (optional)
        provider_config: Optional provider configuration dict with keys:
            - name: "openrouter" or "dashscope"
            - model: Model ID (e.g., "anthropic/claude-sonnet-4" or "deepseek-v3.2")
            - api_key: API key for the provider

    Yields:
        StreamEvent objects (TextDeltaEvent, ToolCallEvent, ToolResultEvent, DoneEvent, ErrorEvent, CompressionEvent, ApprovalRequiredEvent, SteeringEvent)

    Example:
        async for event in stream_agent_response("Read main.tex", "/path/to/project"):
            yield event.to_sse()  # For SSE endpoints
    """
    # Process steering if enabled
    effective_message = message
    if enable_steering:
        from agent.steering import get_steering_manager, check_and_inject_steering

        steering_manager = get_steering_manager()
        effective_message, steering_used = await check_and_inject_steering(
            steering_manager, message, session_id
        )

        if steering_used:
            # Emit steering event
            preview = steering_used[0].content[:100] + "..." if len(steering_used[0].content) > 100 else steering_used[0].content
            yield SteeringEvent(
                messages_count=len(steering_used),
                content_preview=preview,
            )
            logger.info(f"Steering: Injected {len(steering_used)} messages")

    # Set up HITL if enabled
    hitl_manager = None
    event_queue: Optional[asyncio.Queue] = None

    logger.info(f"HITL enabled: {enable_hitl}")

    if enable_hitl:
        from agent.hitl import get_hitl_manager

        hitl_manager = get_hitl_manager()
        event_queue = asyncio.Queue()
        logger.info(f"HITL manager created: {hitl_manager}, approval_required={hitl_manager.config.approval_required}")

        # Set up callback to emit approval events to stream
        async def on_approval_request(request):
            logger.info(f"HITL approval request: tool={request.tool_name}, args_keys={list(request.tool_args.keys())}")
            logger.info(f"HITL tool_args: old_string={len(request.tool_args.get('old_string', ''))} chars, new_string={len(request.tool_args.get('new_string', ''))} chars")
            await event_queue.put(ApprovalRequiredEvent(
                request_id=request.request_id,
                tool_name=request.tool_name,
                tool_args=request.tool_args,
            ))

        hitl_manager.set_event_callback(on_approval_request)

    # Set up research preference HITL callbacks (domain + venue)
    if event_queue:
        from agent.venue_hitl import get_research_preference_manager

        research_pref_manager = get_research_preference_manager()

        # Domain preference callback
        async def on_domain_preference_request(request):
            await event_queue.put(DomainPreferenceRequestEvent(
                request_id=request.request_id,
                topic=request.topic,
                suggested_domain=request.suggested_domain,
            ))

        # Venue preference callback
        async def on_venue_preference_request(request):
            await event_queue.put(VenuePreferenceRequestEvent(
                request_id=request.request_id,
                topic=request.topic,
                domain=request.domain,
                suggested_venues=request.suggested_venues,
            ))

        research_pref_manager.set_domain_event_callback(on_domain_preference_request)
        research_pref_manager.set_venue_event_callback(on_venue_preference_request)

    # Set up planning if enabled
    plan_manager = None
    if enable_planning:
        from agent.planning import get_plan_manager
        plan_manager = get_plan_manager()

        # Load any existing plan from session
        effective_session_id = session_id or "default"
        existing_plan = await plan_manager.load_from_session(effective_session_id, project_path)
        if existing_plan:
            logger.info(f"Restored plan '{existing_plan.plan_id}' from session {effective_session_id}")

        # Set up callbacks to emit plan events if we have an event queue
        if event_queue:
            async def on_plan_created(plan):
                logger.info(f"Plan created: {plan.plan_id} with {len(plan.steps)} steps")
                # Include step data for UI rendering
                steps_data = [
                    {
                        "step_number": s.step_number,
                        "title": s.title,
                        "description": s.description,
                        "status": s.status.value,
                        "files": s.files,
                    }
                    for s in plan.steps
                ]
                await event_queue.put(PlanCreatedEvent(
                    plan_id=plan.plan_id,
                    goal=plan.goal,
                    steps_count=len(plan.steps),
                    complexity=plan.complexity,
                    steps=steps_data,
                ))

            async def on_step_started(plan, step):
                logger.info(f"Step started: {step.step_number}. {step.title}")
                progress = plan.progress
                await event_queue.put(PlanStepEvent(
                    plan_id=plan.plan_id,
                    step_number=step.step_number,
                    step_title=step.title,
                    status="started",
                    progress_percent=progress["percent"],
                ))

            async def on_step_completed(plan, step):
                status = "completed" if step.status.value == "completed" else step.status.value
                logger.info(f"Step {status}: {step.step_number}. {step.title}")
                progress = plan.progress
                await event_queue.put(PlanStepEvent(
                    plan_id=plan.plan_id,
                    step_number=step.step_number,
                    step_title=step.title,
                    status=status,
                    progress_percent=progress["percent"],
                ))

            async def on_plan_completed(plan):
                progress = plan.progress
                logger.info(f"Plan completed: {plan.plan_id}")
                await event_queue.put(PlanCompletedEvent(
                    plan_id=plan.plan_id,
                    goal=plan.goal,
                    total_steps=progress["total"],
                    completed_steps=progress["completed"],
                    failed_steps=progress["failed"],
                ))

            plan_manager.set_callbacks(
                on_plan_created=on_plan_created,
                on_step_started=on_step_started,
                on_step_completed=on_step_completed,
                on_plan_completed=on_plan_completed,
            )

    # Extract provider name for prompt adjustments
    provider_name = "openrouter"
    if provider_config and provider_config.get("name"):
        provider_name = provider_config.get("name")

    deps = AuraDeps(
        project_path=project_path,
        project_name=project_name,
        hitl_manager=hitl_manager,
        plan_manager=plan_manager,
        session_id=session_id or "default",
        provider_name=provider_name,
    )
    logger.info(f"Created AuraDeps with hitl_manager={deps.hitl_manager}, provider={provider_name}")

    # Use session-based history instead of frontend history
    # This preserves the full PydanticAI message structure including tool calls
    effective_session_id = session_id or "default"
    processed_history = get_session_history_from_disk(project_path, effective_session_id)

    # Handle compression if enabled and history provided
    if auto_compress and processed_history:
        try:
            compressor = get_compressor()
            tokens_before = compressor.counter.count(processed_history)
            original_count = len(processed_history)

            compressed_history, was_compressed = await compress_if_needed(processed_history)

            if was_compressed:
                tokens_after = compressor.counter.count(compressed_history)
                logger.info(
                    f"Compressed history: {original_count} -> {len(compressed_history)} messages, "
                    f"{tokens_before} -> {tokens_after} tokens"
                )
                yield CompressionEvent(
                    original_messages=original_count,
                    compressed_messages=len(compressed_history),
                    estimated_tokens_before=tokens_before,
                    estimated_tokens_after=tokens_after,
                )
                processed_history = compressed_history
        except Exception as e:
            logger.warning(f"Compression failed, using original history: {e}")
            # Continue with original history on compression failure

    # Resolve model based on provider config
    model_override = None

    if provider_config:
        provider_name = provider_config.get("name", "openrouter")
        api_key = provider_config.get("api_key", "")

        # Validate API key for OpenRouter
        if provider_name == "openrouter" and not api_key:
            yield ErrorEvent(
                message="OpenRouter API key not configured. "
                "Please go to Settings and enter your OpenRouter API key. "
                "Get your API key at: https://openrouter.ai/keys"
            )
            return

        # Create model with API key
        if api_key:
            from agent.providers import get_model
            try:
                model_override = get_model(
                    provider=provider_name,
                    model_id=provider_config.get("model"),
                    api_key=api_key,
                )
                logger.info(f"Using {provider_name} model: {provider_config.get('model')}")
            except Exception as e:
                logger.error(f"Failed to get model from provider config: {e}")
                yield ErrorEvent(message=f"Provider error: {e}")
                return

    try:
        if enable_hitl and event_queue:
            # HITL mode: Run agent with event queue for approval events
            async for event in _stream_with_hitl(
                effective_message, deps, processed_history, event_queue, effective_session_id,
                model_override=model_override,
            ):
                yield event
        else:
            # Standard mode: Direct streaming
            async for event in _stream_standard(
                effective_message, deps, processed_history, effective_session_id,
                model_override=model_override,
            ):
                yield event

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield ErrorEvent(message=str(e))


async def _stream_standard(
    message: str,
    deps: AuraDeps,
    message_history: list,
    session_id: str,
    model_override=None,
) -> AsyncIterator[StreamEvent]:
    """Standard streaming without HITL."""
    # Track pending tool calls to emit results after they complete
    pending_tool_calls: list[tuple[str, str]] = []  # (tool_name, tool_call_id)

    # Use model override if provided, otherwise use default
    iter_kwargs = {
        "deps": deps,
        "message_history": message_history,
        "usage_limits": UsageLimits(request_limit=200),
    }
    if model_override:
        iter_kwargs["model"] = model_override

    async with aura_agent.iter(message, **iter_kwargs) as run:
        async for node in run:
            # If we have pending tool calls and we're now at a new model request,
            # that means the tools have completed. We'll emit generic success for them.
            if pending_tool_calls and isinstance(node, ModelRequestNode):
                for tool_name, tool_call_id in pending_tool_calls:
                    yield ToolResultEvent(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        result="(completed)",
                    )
                pending_tool_calls.clear()

            if isinstance(node, UserPromptNode):
                continue

            elif isinstance(node, ModelRequestNode):
                async with node.stream(run.ctx) as stream:
                    async for text in stream.stream_text(delta=True):
                        yield TextDeltaEvent(content=text)

            elif isinstance(node, CallToolsNode):
                for part in node.model_response.parts:
                    if isinstance(part, ToolCallPart):
                        try:
                            args = part.args_as_dict()
                        except Exception as e:
                            logger.error(f"Failed to parse tool call args for {part.tool_name}: {e}")
                            # Try to get raw args for debugging
                            raw_args = getattr(part, 'args', None)
                            if raw_args:
                                logger.error(f"Raw args (first 200 chars): {str(raw_args)[:200]}")
                            args = {"_parse_error": str(e)}
                        tool_call_id = part.tool_call_id or ""
                        pending_tool_calls.append((part.tool_name, tool_call_id))
                        yield ToolCallEvent(
                            tool_name=part.tool_name,
                            tool_call_id=tool_call_id,
                            args=args,
                        )

            elif isinstance(node, End):
                # Emit any remaining pending tool results
                for tool_name, tool_call_id in pending_tool_calls:
                    yield ToolResultEvent(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        result="(completed)",
                    )
                pending_tool_calls.clear()

    result = run.result
    usage = result.usage()

    # Save the updated message history for this session
    # all_messages() returns the complete conversation including new messages
    all_messages = result.all_messages()
    save_session_history_to_disk(deps.project_path, session_id, all_messages)
    logger.info(f"Saved {len(all_messages)} messages to session {session_id}")

    yield DoneEvent(
        output=result.output or "",
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0,
    )


async def _stream_with_hitl(
    message: str,
    deps: AuraDeps,
    message_history: list,
    event_queue: asyncio.Queue,
    session_id: str,
    model_override=None,
) -> AsyncIterator[StreamEvent]:
    """
    Streaming with HITL support.

    Uses asyncio.Queue to receive approval events from tools while
    the agent is processing. The agent runs in a background task,
    pushing events to the queue. This generator reads from the queue
    and yields events.
    """
    # Queue for all events (both agent events and HITL events)
    done_event = asyncio.Event()
    agent_error = None

    # Prepare iter kwargs with optional model override
    iter_kwargs = {
        "deps": deps,
        "message_history": message_history,
        "usage_limits": UsageLimits(request_limit=200),
    }
    if model_override:
        iter_kwargs["model"] = model_override

    async def run_agent_task():
        """Run agent and push events to queue."""
        nonlocal agent_error
        # Track pending tool calls to emit results after they complete
        pending_tool_calls: list[tuple[str, str]] = []  # (tool_name, tool_call_id)

        try:
            async with aura_agent.iter(message, **iter_kwargs) as run:
                async for node in run:
                    # If we have pending tool calls and we're now at a new model request,
                    # that means the tools have completed
                    if pending_tool_calls and isinstance(node, ModelRequestNode):
                        for tool_name, tool_call_id in pending_tool_calls:
                            await event_queue.put(ToolResultEvent(
                                tool_name=tool_name,
                                tool_call_id=tool_call_id,
                                result="(completed)",
                            ))
                        pending_tool_calls.clear()

                    if isinstance(node, UserPromptNode):
                        continue

                    elif isinstance(node, ModelRequestNode):
                        async with node.stream(run.ctx) as stream:
                            async for text in stream.stream_text(delta=True):
                                await event_queue.put(TextDeltaEvent(content=text))

                    elif isinstance(node, CallToolsNode):
                        for part in node.model_response.parts:
                            if isinstance(part, ToolCallPart):
                                try:
                                    args = part.args_as_dict()
                                except Exception as e:
                                    logger.error(f"Failed to parse tool call args for {part.tool_name}: {e}")
                                    raw_args = getattr(part, 'args', None)
                                    if raw_args:
                                        logger.error(f"Raw args (first 200 chars): {str(raw_args)[:200]}")
                                    args = {"_parse_error": str(e)}
                                tool_call_id = part.tool_call_id or ""
                                pending_tool_calls.append((part.tool_name, tool_call_id))
                                await event_queue.put(ToolCallEvent(
                                    tool_name=part.tool_name,
                                    tool_call_id=tool_call_id,
                                    args=args,
                                ))

                    elif isinstance(node, End):
                        # Emit any remaining pending tool results
                        for tool_name, tool_call_id in pending_tool_calls:
                            await event_queue.put(ToolResultEvent(
                                tool_name=tool_name,
                                tool_call_id=tool_call_id,
                                result="(completed)",
                            ))
                        pending_tool_calls.clear()

            result = run.result
            usage = result.usage()

            # Save the updated message history for this session
            all_messages = result.all_messages()
            save_session_history_to_disk(deps.project_path, session_id, all_messages)
            logger.info(f"Saved {len(all_messages)} messages to session {session_id}")

            await event_queue.put(DoneEvent(
                output=result.output or "",
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
            ))

        except Exception as e:
            agent_error = e
            await event_queue.put(ErrorEvent(message=str(e)))

        finally:
            done_event.set()

    # Start agent in background
    agent_task = asyncio.create_task(run_agent_task())

    try:
        # Yield events as they come
        while not done_event.is_set() or not event_queue.empty():
            try:
                # Use timeout to periodically check done_event
                event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                yield event

                # If it's a done or error event, we're finished
                if isinstance(event, (DoneEvent, ErrorEvent)):
                    break

            except asyncio.TimeoutError:
                # No event yet, continue waiting
                continue

    finally:
        # Ensure agent task is cleaned up
        if not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass


async def stream_agent_sse(
    message: str,
    project_path: str,
    project_name: str = "",
    message_history: list = None,
    enable_hitl: bool = True,  # Enabled by default for file safety
    enable_steering: bool = False,
    session_id: str | None = None,
    provider_config: dict | None = None,
) -> AsyncIterator[str]:
    """
    Stream agent response as SSE-formatted strings.

    Convenience wrapper for FastAPI StreamingResponse.

    Args:
        message: User's message
        project_path: Path to the LaTeX project
        project_name: Optional project name
        message_history: Optional conversation history
        enable_hitl: Whether to enable HITL approval (default: True)
        enable_steering: Whether to enable steering messages (default: False)
        session_id: Session ID for steering isolation (optional)
        provider_config: Optional provider configuration dict with keys:
            - name: "openrouter" or "dashscope"
            - model: Model ID (e.g., "anthropic/claude-sonnet-4" or "deepseek-v3.2")
            - api_key: API key for the provider

    Yields:
        SSE-formatted strings ready for StreamingResponse

    Example:
        @app.post("/chat/stream")
        async def chat_stream(request: ChatRequest):
            return StreamingResponse(
                stream_agent_sse(request.message, request.project_path),
                media_type="text/event-stream"
            )
    """
    async for event in stream_agent_response(
        message=message,
        project_path=project_path,
        project_name=project_name,
        message_history=message_history,
        enable_hitl=enable_hitl,
        enable_steering=enable_steering,
        session_id=session_id,
        provider_config=provider_config,
    ):
        yield event.to_sse()


# =============================================================================
# Non-streaming Runner
# =============================================================================

async def run_agent(
    message: str,
    project_path: str,
    project_name: str = "",
    message_history: list = None,
    auto_compress: bool = True,
    enable_steering: bool = False,
    enable_planning: bool = True,
    session_id: str | None = None,
) -> dict:
    """
    Run agent and return complete response (non-streaming).

    Args:
        message: User's message
        project_path: Path to the LaTeX project
        project_name: Optional project name
        message_history: Optional conversation history
        auto_compress: Whether to automatically compress long histories (default: True)
        enable_steering: Whether to check for steering messages (default: False)
        enable_planning: Whether to enable planning features (default: True)
        session_id: Session ID for steering isolation (optional)

    Returns:
        Dictionary with output, usage, new_messages, compression_info, steering_info, and planning_info
    """
    # Set up planning if enabled
    plan_manager = None
    if enable_planning:
        from agent.planning import get_plan_manager
        plan_manager = get_plan_manager()

    deps = AuraDeps(
        project_path=project_path,
        project_name=project_name,
        plan_manager=plan_manager,
        session_id=session_id or "default",
    )

    # Process steering if enabled
    effective_message = message
    steering_info = None
    if enable_steering:
        from agent.steering import get_steering_manager, check_and_inject_steering

        steering_manager = get_steering_manager()
        effective_message, steering_used = await check_and_inject_steering(
            steering_manager, message, session_id
        )

        if steering_used:
            steering_info = {
                "messages_injected": len(steering_used),
                "priorities": [m.priority for m in steering_used],
            }
            logger.info(f"Steering: Injected {len(steering_used)} messages into run_agent")

    # Use session-based history instead of frontend history
    effective_session_id = session_id or "default"
    processed_history = get_session_history_from_disk(project_path, effective_session_id)
    compression_info = None

    # Handle compression if enabled and history provided
    if auto_compress and processed_history:
        try:
            compressor = get_compressor()
            tokens_before = compressor.counter.count(processed_history)
            original_count = len(processed_history)

            compressed_history, was_compressed = await compress_if_needed(processed_history)

            if was_compressed:
                tokens_after = compressor.counter.count(compressed_history)
                logger.info(
                    f"Compressed history: {original_count} -> {len(compressed_history)} messages, "
                    f"{tokens_before} -> {tokens_after} tokens"
                )
                compression_info = {
                    "original_messages": original_count,
                    "compressed_messages": len(compressed_history),
                    "tokens_before": tokens_before,
                    "tokens_after": tokens_after,
                    "tokens_saved": tokens_before - tokens_after,
                }
                processed_history = compressed_history
        except Exception as e:
            logger.warning(f"Compression failed, using original history: {e}")

    result = await aura_agent.run(effective_message, deps=deps, message_history=processed_history)
    usage = result.usage()

    # Save the updated message history for this session
    all_messages = result.all_messages()
    save_session_history_to_disk(project_path, effective_session_id, all_messages)
    logger.info(f"Saved {len(all_messages)} messages to session {effective_session_id}")

    response = {
        "output": result.output,
        "usage": {
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
        },
        "new_messages": result.new_messages(),
    }

    if compression_info:
        response["compression"] = compression_info

    if steering_info:
        response["steering"] = steering_info

    # Include planning info if plan was used/created
    if plan_manager:
        plan = await plan_manager.get_plan(session_id or "default")
        if plan:
            response["planning"] = {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "status": plan.status.value,
                "progress": plan.progress,
            }

    return response
