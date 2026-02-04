# Error Handling Standardization Design

> Phase 3: Unified error codes, ToolError exceptions, and structured logging

## Overview

Standardize error handling across all agent tools using:
1. `ErrorCode` enum for programmatic error identification
2. `ToolError` exception class for structured errors
3. `structlog` for consistent, queryable logging

## Components

### 1. Error Model (`backend/agent/errors.py`)

```python
class ErrorCode(Enum):
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PATH_ESCAPE = "PATH_ESCAPE"
    COMPILATION_FAILED = "COMPILATION_FAILED"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"
    INVALID_INPUT = "INVALID_INPUT"
    # ... more codes

@dataclass
class ToolError(Exception):
    code: ErrorCode
    message: str
    details: dict = field(default_factory=dict)
```

### 2. Structured Logging (`backend/agent/logging.py`)

```python
setup_logging(json_output=False, level="INFO")
logger = get_logger("tools")

# In tools:
log_tool_call(logger, "read_file", filepath=filepath)
log_tool_success(logger, "read_file", lines=100)
log_tool_error(logger, "read_file", "FILE_NOT_FOUND", "File not found")
```

### 3. Tool Refactoring Pattern

Before:
```python
if not full_path.exists():
    return f"Error: File not found: {filepath}"
```

After:
```python
if not full_path.exists():
    log_tool_error(logger, "read_file", "FILE_NOT_FOUND", f"File not found: {filepath}")
    raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")
```

## Refactored Tools

| Tool | Errors Handled |
|------|----------------|
| `read_file` | FILE_NOT_FOUND, PATH_ESCAPE, PERMISSION_DENIED, INVALID_PATH |
| `edit_file` | FILE_NOT_FOUND, PATH_ESCAPE, PERMISSION_DENIED, INVALID_INPUT |
| `write_file` | PATH_ESCAPE, PERMISSION_DENIED |
| `list_files` | FILE_NOT_FOUND, PATH_ESCAPE, PERMISSION_DENIED, INVALID_PATH |
| `find_files` | INTERNAL_ERROR |
| `compile_latex` | COMPILATION_FAILED, NOT_IMPLEMENTED |
| `check_latex_syntax` | FILE_NOT_FOUND, PERMISSION_DENIED |
| `delegate_to_subagent` | INVALID_INPUT, API_ERROR |

## Configuration

Environment variables:
- `AURA_LOG_JSON=1` - Enable JSON output (production)
- `AURA_LOG_LEVEL=DEBUG` - Set log level

## Benefits

1. **Frontend**: Can parse `error.code` for i18n or specific handling
2. **Debugging**: Structured logs are queryable (`jq`, log aggregators)
3. **Monitoring**: Consistent error codes enable alerting
4. **Consistency**: All tools follow the same error pattern
