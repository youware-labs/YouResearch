"""
Structured Logging for Aura Agent

Provides consistent, structured logging across the application
using structlog for better observability and debugging.

Usage:
    from agent.logging import get_logger, setup_logging

    # At application startup
    setup_logging(json_output=False, level="INFO")

    # In modules
    logger = get_logger("tools")
    logger.info("tool_called", tool="read_file", filepath="/path/to/file")
    logger.error("tool_failed", tool="edit_file", error="File not found", code="FILE_NOT_FOUND")
"""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import Processor


def setup_logging(
    json_output: bool = False,
    level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        json_output: If True, output JSON lines (for production).
                     If False, output colored console (for development).
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
    """
    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors for all outputs
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        # Production: JSON lines for log aggregation
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: colored console output
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Also configure standard library logging for third-party libs
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=log_level,
        stream=sys.stderr,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Optional logger name (e.g., "tools", "streaming", "api")

    Returns:
        A bound structlog logger
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()


def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables to all subsequent log messages.

    Useful for request-scoped context like session_id, project_path.

    Example:
        bind_context(session_id="abc123", project_path="/path/to/project")
        logger.info("processing")  # Will include session_id and project_path
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


# Convenience function for logging tool calls
def log_tool_call(logger: structlog.BoundLogger, tool_name: str, **kwargs: Any) -> None:
    """Log a tool call with standard fields."""
    logger.info("tool_called", tool=tool_name, **kwargs)


def log_tool_success(logger: structlog.BoundLogger, tool_name: str, **kwargs: Any) -> None:
    """Log a successful tool completion."""
    logger.info("tool_success", tool=tool_name, **kwargs)


def log_tool_error(
    logger: structlog.BoundLogger,
    tool_name: str,
    error_code: str,
    error_message: str,
    **kwargs: Any,
) -> None:
    """Log a tool failure with standard fields."""
    logger.warning("tool_failed", tool=tool_name, code=error_code, error=error_message, **kwargs)
