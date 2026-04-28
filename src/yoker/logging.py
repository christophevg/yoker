"""Structured logging configuration for Yoker.

Provides structlog-based logging with:
- Console and file handlers
- Timing context manager
- Thread-local context binding

This module is in the Support Layer of the architecture, providing
infrastructure logging separate from the domain Event system.
"""

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import local
from typing import Any, Literal

import structlog
from structlog.typing import EventDict, Processor


class LoggingContext:
  """Thread-local context for structured logging.

  Provides a way to bind context values that will be included in
  all log messages within a scope.

  Example:
    with LoggingContext.bind(session_id="abc123"):
      log.info("turn_started", message="Hello")
      # Output includes session_id="abc123"

  Note:
    Uses thread-local storage for thread safety.
  """

  _thread_local = local()

  @classmethod
  def _get_context(cls) -> dict[str, Any]:
    """Get the current thread-local context."""
    context = getattr(cls._thread_local, "context", None)
    if context is None:
      context = {}
      cls._thread_local.context = context
    return context

  @classmethod
  def bind(cls, **kwargs: Any) -> "_ContextBinder":
    """Bind context values for all logs within a scope.

    Args:
      **kwargs: Key-value pairs to add to logging context.

    Returns:
      Context manager that removes bindings on exit.

    Example:
      with LoggingContext.bind(session_id="abc123", turn=1):
        log.info("processing")
    """
    return _ContextBinder(kwargs)


class _ContextBinder:
  """Context manager for LoggingContext.bind()."""

  def __init__(self, bindings: dict[str, Any]) -> None:
    """Initialize with bindings to add."""
    self._bindings = bindings
    self._previous: dict[str, Any] | None = None

  def __enter__(self) -> "_ContextBinder":
    """Add bindings to context."""
    self._previous = LoggingContext._get_context().copy()
    LoggingContext._get_context().update(self._bindings)
    return self

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
    """Restore previous context."""
    if self._previous is not None:
      LoggingContext._thread_local.context = self._previous


def _add_context(logger: logging.Logger, method_name: str, event_dict: EventDict) -> EventDict:
  """Processor to add thread-local context to log entries.

  Args:
    logger: The wrapped logger.
    method_name: The log method name.
    event_dict: The event dictionary.

  Returns:
    Event dict with context values merged in.
  """
  context = LoggingContext._get_context()
  event_dict.update(context)
  return event_dict


def _rename_log_level(logger: logging.Logger, method_name: str, event_dict: EventDict) -> EventDict:
  """Processor to rename 'level' to 'severity' for compatibility.

  Args:
    logger: The wrapped logger.
    method_name: The log method name.
    event_dict: The event dictionary.

  Returns:
    Event dict with 'severity' instead of 'level'.
  """
  if "level" in event_dict:
    event_dict["severity"] = event_dict.pop("level")
  return event_dict


def configure_logging(
  level: str = "INFO",
  log_file: Path | None = None,
  format: Literal["json", "text"] = "text",
  console: bool = True,
) -> None:
  """Configure structlog for the application.

  Sets up structured logging with console output and optional file output.
  Should be called once at application startup.

  Args:
    level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    log_file: Optional file path for log output.
    format: Output format (json for production, text for development).
    console: Whether to output to console (default True).

  Example:
    configure_logging(
      level="DEBUG",
      log_file=Path("logs/yoker.log"),
      format="json",
    )
  """
  # Convert level string to int
  log_level = getattr(logging, level.upper(), logging.INFO)

  # Configure standard library logging
  handlers: list[logging.Handler] = []

  # Console handler (optional)
  if console:
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    handlers.append(console_handler)

  # File handler (if specified)
  if log_file is not None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    handlers.append(file_handler)

  # Configure standard library logging
  logging.basicConfig(
    level=log_level,
    handlers=handlers,
    format="%(message)s",  # structlog handles formatting
  )

  # Configure structlog processors
  shared_processors: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.StackInfoRenderer(),
    structlog.dev.set_exc_info,
    structlog.processors.TimeStamper(fmt="iso"),
    _add_context,
  ]

  # Configure structlog processors based on format
  if format == "json":
    # JSON format for production
    shared_processors.append(structlog.processors.format_exc_info)
    final_processors: list[Processor] = [structlog.processors.JSONRenderer()]
  else:
    # Human-readable format for development
    shared_processors.append(_rename_log_level)
    final_processors = [structlog.dev.ConsoleRenderer(colors=True)]

  # Configure structlog
  # If no handlers and console disabled, use minimal configuration (no output)
  if not handlers:
    # No output - configure with minimal processors and CRITICAL level
    structlog.configure(
      processors=[],
      wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
      context_class=dict,
      logger_factory=structlog.stdlib.LoggerFactory(),
      cache_logger_on_first_use=True,
    )
  else:
    # Normal configuration with output
    structlog.configure(
      processors=shared_processors + final_processors,
      wrapper_class=structlog.make_filtering_bound_logger(log_level),
      context_class=dict,
      logger_factory=structlog.PrintLoggerFactory(),
      cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
  """Get a configured logger for a module.

  Args:
    name: Module name (typically __name__).

  Returns:
    Configured structlog logger.

  Example:
    log = get_logger(__name__)
    log.info("session_started", model="llama3.2")
  """
  logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
  return logger


@contextmanager
def log_timing(
  operation: str,
  log_level: str = "debug",
  **context: Any,
) -> Iterator[None]:
  """Context manager to log timing for an operation.

  Automatically logs the duration when the context exits.

  Args:
    operation: Operation name for the log message.
    log_level: Log level for timing message (default: debug).
    **context: Additional context to include in log.

  Example:
    with log_timing("tool_execution", tool="read", file="test.py"):
      result = read_file("test.py")
    # Logs: "tool_execution" with duration_ms and context
  """
  log = get_logger(__name__)
  start = time.perf_counter()
  try:
    yield
  finally:
    duration_ms = (time.perf_counter() - start) * 1000
    getattr(log, log_level)(
      operation,
      duration_ms=round(duration_ms, 2),
      **context,
    )


__all__ = [
  "LoggingContext",
  "configure_logging",
  "get_logger",
  "log_timing",
]
