# Session Persistence Design

> Plans stored within ChatSession for conversation continuity

## Overview

Persist execution plans alongside chat sessions by embedding them in the existing `ChatSession` JSON files. This ensures plans survive backend restarts and remain contextually linked to their conversations.

## Current State

- **Sessions**: Persisted to `{project}/.aura/chat_session_{id}.json` via `ChatSession` class
- **Plans**: In-memory only (`PlanManager._plans` dict), lost on restart

## Design

### ChatSession Schema Extension

```json
{
  "session_id": "abc123",
  "name": "Chat abc123",
  "created_at": "2026-02-04T10:00:00Z",
  "updated_at": "2026-02-04T10:05:00Z",
  "message_count": 12,
  "messages": [...],
  "active_plan": {
    "plan_id": "12345678",
    "goal": "Add bibliography section",
    "status": "in_progress",
    "complexity": 3,
    "steps": [
      {
        "step_id": "a1b2c3",
        "step_number": 1,
        "title": "Read existing structure",
        "status": "completed"
      }
    ]
  },
  "plan_history": [
    { "plan_id": "...", "goal": "...", "status": "completed", ... }
  ]
}
```

### New Fields

| Field | Type | Description |
|-------|------|-------------|
| `active_plan` | `dict \| None` | Currently executing plan |
| `plan_history` | `list[dict]` | Completed/cancelled plans (max 10) |

### PlanManager Integration

```python
class PlanManager:
    async def create_plan(self, ..., session_id: str, project_path: str) -> Plan:
        plan = Plan(...)
        self._plans[session_id] = plan
        await self._persist_plan(plan, session_id, project_path)
        return plan

    async def _persist_plan(self, plan: Plan, session_id: str, project_path: str):
        session = ChatSession.load(project_path, session_id)
        if session:
            session.active_plan = plan.to_dict()
            session.save()

    async def load_from_session(self, session_id: str, project_path: str) -> Plan | None:
        session = ChatSession.load(project_path, session_id)
        if session and session.active_plan:
            plan = Plan.from_dict(session.active_plan)
            self._plans[session_id] = plan
            return plan
        return None
```

### Data Flow

```
Stream starts
    │
    ▼
load_from_session() ──► Restore active_plan to memory
    │
    ▼
Agent creates plan
    │
    ▼
_persist_plan() ──► Save to session JSON
    │
    ▼
Step updates ──► _persist_plan()
    │
    ▼
Plan completes
    │
    ▼
archive_plan() ──► Move to plan_history, clear active_plan
```

## Implementation

### Files to Modify

1. **backend/agent/streaming.py**
   - Add `active_plan`, `plan_history` fields to `ChatSession`
   - Update `save()`, `load()` methods
   - Add `set_active_plan()`, `archive_plan()` helpers

2. **backend/agent/planning.py**
   - Add `project_path` parameter to persistence methods
   - Add `_persist_plan()`, `load_from_session()` methods
   - Modify `create_plan()`, `update_step()`, `cancel_plan()` to persist

### Migration

Existing session files without `active_plan` field will load with `None` (backward compatible).

## Testing

1. Create plan, restart backend, verify plan restored
2. Complete plan, verify moved to history
3. Load old session file without plan fields (backward compat)
