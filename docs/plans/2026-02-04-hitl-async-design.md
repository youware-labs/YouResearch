# HITL Async Refactoring Design

> Phase 4: Non-blocking approval flow with WebSocket real-time updates
>
> **Status**: Backend implementation complete

## Overview

Refactor HITL from blocking (agent waits 5min for approval) to async (agent continues, operations queue for approval).

## Current vs New Architecture

### Current (Blocking)
```
User message → Agent runs → Tool needs approval → Agent blocks up to 5min
                                    ↓
                          SSE: approval_required
                                    ↓
                          User approves via REST
                                    ↓
                          Agent unblocks, executes tool
```

### New (Non-blocking)
```
User message → Agent runs → Tool needs approval → Store operation → Agent returns immediately
                                    ↓                     ↓
                          WSS: pending_operation    Operations queue in UI
                                    ↓                     ↓
                          User batch approves    Execute approved ops
                                    ↓                     ↓
                          WSS: execution_result   Update tex panel with diff
```

## Components

### 1. Pending Operation Store (`backend/agent/hitl_store.py`)

```python
class OperationStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"

@dataclass
class PendingOperation:
    operation_id: str
    session_id: str  # Which chat session this belongs to
    tool_name: str
    tool_args: dict
    status: OperationStatus
    created_at: datetime
    expires_at: datetime  # Auto-expire after timeout
    result: str | None = None
    error: str | None = None

    # For diff preview
    file_path: str | None = None  # Extracted from tool_args if applicable
    old_content: str | None = None  # Read from file when operation created
    new_content: str | None = None  # Computed for edit_file/write_file

class HITLStore:
    """Thread-safe store for pending operations."""

    async def add_operation(self, op: PendingOperation) -> str
    async def get_operation(self, op_id: str) -> PendingOperation | None
    async def get_pending_by_session(self, session_id: str) -> list[PendingOperation]
    async def approve(self, op_id: str) -> bool
    async def reject(self, op_id: str, reason: str) -> bool
    async def batch_approve(self, op_ids: list[str]) -> dict[str, bool]
    async def batch_reject(self, op_ids: list[str], reason: str) -> dict[str, bool]
    async def cleanup_expired() -> int
```

### 2. WebSocket Handler (`backend/agent/hitl_ws.py`)

```python
class HITLWebSocket:
    """WebSocket manager for real-time HITL notifications."""

    # Connected clients by session_id
    _connections: dict[str, list[WebSocket]]

    async def connect(self, websocket: WebSocket, session_id: str)
    async def disconnect(self, websocket: WebSocket, session_id: str)

    # Push events to clients
    async def notify_pending(self, session_id: str, operation: PendingOperation)
    async def notify_status_change(self, session_id: str, op_id: str, status: OperationStatus)
    async def notify_execution_result(self, session_id: str, op_id: str, result: str)

# WebSocket message types
@dataclass
class WSMessage:
    type: str  # "pending", "status", "result"
    data: dict
```

### 3. Executor Service (`backend/agent/hitl_executor.py`)

```python
class HITLExecutor:
    """Execute approved operations."""

    async def execute_operation(self, op_id: str, project_path: str) -> str:
        """
        Execute an approved operation.

        1. Get operation from store
        2. Verify status is APPROVED
        3. Execute the tool logic directly (not through agent)
        4. Update operation status and result
        5. Notify via WebSocket
        """
```

### 4. Refactored Tool Pattern

Before (blocking):
```python
@aura_agent.tool
async def edit_file(ctx, filepath, old_string, new_string):
    should_proceed, rejection_msg, modified_args = await _check_hitl(ctx, "edit_file", {...})
    if not should_proceed:
        return rejection_msg
    # Execute...
```

After (non-blocking):
```python
@aura_agent.tool
async def edit_file(ctx, filepath, old_string, new_string):
    if ctx.deps.hitl_store and ctx.deps.hitl_store.needs_approval("edit_file"):
        # Queue operation for approval instead of blocking
        op_id = await ctx.deps.hitl_store.add_operation(
            tool_name="edit_file",
            tool_args={"filepath": filepath, "old_string": old_string, "new_string": new_string},
            session_id=ctx.deps.session_id,
            # Compute diff preview
            file_path=filepath,
            old_content=current_file_content,
            new_content=computed_new_content,
        )
        # Notify via WebSocket
        await ctx.deps.hitl_ws.notify_pending(ctx.deps.session_id, op)

        # Return immediately with pending status
        return f"[PENDING:{op_id}] Edit queued for approval: {filepath}"

    # Execute directly if no approval needed
    ...
```

## API Endpoints

### REST Endpoints (existing, modified)

```
GET  /api/hitl/pending?session_id=xxx     # Get all pending ops for session
POST /api/hitl/approve                     # Approve single operation
POST /api/hitl/reject                      # Reject single operation
POST /api/hitl/batch-approve               # Approve multiple operations
POST /api/hitl/batch-reject                # Reject multiple operations
```

### WebSocket Endpoint (new)

```
WS /ws/hitl/{session_id}
```

Messages:
```json
// Server → Client: New pending operation
{
  "type": "pending",
  "data": {
    "operation_id": "abc123",
    "tool_name": "edit_file",
    "tool_args": {...},
    "file_path": "main.tex",
    "diff_preview": {
      "old_content": "...",
      "new_content": "..."
    },
    "created_at": "2026-02-04T..."
  }
}

// Server → Client: Status change
{
  "type": "status",
  "data": {
    "operation_id": "abc123",
    "status": "approved"
  }
}

// Server → Client: Execution result
{
  "type": "result",
  "data": {
    "operation_id": "abc123",
    "status": "completed",
    "result": "Successfully edited main.tex"
  }
}
```

## Frontend Requirements

### 1. Approval Queue Panel

```
+------------------------------------------+
| Pending Operations (3)            [Approve All] [Reject All]
+------------------------------------------+
| □ edit_file: main.tex            [View Diff] [✓] [✗]
| □ write_file: refs.bib           [View Diff] [✓] [✗]
| □ edit_file: abstract.tex        [View Diff] [✓] [✗]
+------------------------------------------+
```

### 2. Diff Preview in Tex Panel

When "View Diff" is clicked:
- Show the file content with diff highlighting
- Red background for removed lines (old_string)
- Green background for added lines (new_string)
- Similar to current implementation but works with queued operations

### 3. WebSocket Connection

Connect when session starts, disconnect when session ends.
Handle reconnection on disconnect.

## Migration Strategy

1. **Phase 4a**: Add new components (store, websocket, executor) alongside existing
2. **Phase 4b**: Refactor tools to use new async pattern
3. **Phase 4c**: Update streaming.py to not wait for HITL
4. **Phase 4d**: Add REST endpoints for batch operations
5. **Phase 4e**: Document frontend changes needed

## Benefits

1. **Non-blocking**: Agent doesn't wait, user experience is smoother
2. **Queue visibility**: See all pending operations at once
3. **Batch operations**: Approve/reject multiple at once
4. **Real-time**: WebSocket pushes updates immediately
5. **Diff preview**: Still shows old→new changes in tex panel

## Implementation Notes

### Backend Files Created/Modified

| File | Status | Description |
|------|--------|-------------|
| `backend/agent/hitl_store.py` | ✅ NEW | PendingOperation, OperationStatus, HITLStore |
| `backend/agent/hitl_ws.py` | ✅ NEW | WebSocket manager for real-time notifications |
| `backend/agent/hitl_executor.py` | ✅ NEW | Execute approved operations |
| `backend/agent/pydantic_agent.py` | ✅ MODIFIED | AuraDeps with hitl_mode, async _check_hitl |
| `backend/agent/streaming.py` | ✅ MODIFIED | hitl_mode param, PendingOperationEvent |
| `backend/main.py` | ✅ MODIFIED | WebSocket endpoint, v2 batch APIs |

### How to Use

**Enable async HITL mode:**

```python
# In streaming.py
deps = AuraDeps(
    project_path=project_path,
    hitl_mode="async",  # Use non-blocking mode
    hitl_store=get_hitl_store(),
    hitl_ws=get_hitl_ws_manager(),
)
```

**API v2 endpoints:**

```bash
# Get pending operations
GET /api/hitl/v2/pending?session_id=xxx

# Approve operation
POST /api/hitl/v2/approve {"request_id": "op-123"}

# Batch approve
POST /api/hitl/v2/batch-approve {"operation_ids": ["op-1", "op-2"]}

# Execute after approval
POST /api/hitl/v2/execute {"operation_id": "op-123", "project_path": "/path"}

# WebSocket for real-time updates
WS /ws/hitl/{session_id}
```

### Frontend TODO

- [ ] Connect to WebSocket `/ws/hitl/{session_id}` on session start
- [ ] Create ApprovalQueuePanel component
- [ ] Handle `pending_operation` events to add to queue
- [ ] Handle `operation_executed` events to show results
- [ ] Implement diff viewer with old→new highlighting
- [ ] Add batch approve/reject buttons
