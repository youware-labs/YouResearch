"""
Unified Error Model for Aura Agent Tools

Provides structured error codes and exceptions for consistent
error handling across all agent tools.

Usage:
    from agent.errors import ToolError, ErrorCode

    # Raise structured error
    raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")

    # With details
    raise ToolError(
        ErrorCode.COMPILATION_FAILED,
        "LaTeX compilation failed",
        details={"log": error_log, "line": 42}
    )
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class ErrorCode(Enum):
    """Standard error codes for tool failures."""

    # File operations
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PATH_ESCAPE = "PATH_ESCAPE"
    FILE_EXISTS = "FILE_EXISTS"

    # LaTeX compilation
    COMPILATION_FAILED = "COMPILATION_FAILED"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    MISSING_PACKAGE = "MISSING_PACKAGE"

    # External services
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    CONNECTION_ERROR = "CONNECTION_ERROR"

    # Input validation
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    INVALID_PATH = "INVALID_PATH"

    # Research/PDF
    PDF_PARSE_ERROR = "PDF_PARSE_ERROR"
    ARXIV_ERROR = "ARXIV_ERROR"

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class ToolError(Exception):
    """
    Structured exception for tool failures.

    Attributes:
        code: ErrorCode enum value for programmatic handling
        message: Human-readable error message
        details: Optional dict with additional context (logs, line numbers, etc.)
    """
    code: ErrorCode
    message: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def __repr__(self) -> str:
        return f"ToolError(code={self.code}, message={self.message!r}, details={self.details})"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ToolResult:
    """
    Wrapper for tool results with explicit success/error state.

    Use this when you want to return errors without raising exceptions,
    for example when a tool should gracefully handle partial failures.

    Attributes:
        success: Whether the operation succeeded
        data: Result data on success
        error: ToolError instance on failure
    """
    success: bool
    data: Any = None
    error: ToolError | None = None

    @classmethod
    def ok(cls, data: Any = None) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, code: ErrorCode, message: str, details: dict = None) -> "ToolResult":
        """Create a failed result."""
        return cls(
            success=False,
            error=ToolError(code, message, details or {})
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {"success": self.success}
        if self.success:
            result["data"] = self.data
        else:
            result["error"] = self.error.to_dict() if self.error else None
        return result
