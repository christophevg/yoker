"""Base result and validation types for Yoker tools.

Provides ``ToolResult`` and ``ValidationResult``, the return types used
by the execution wrapper and guardrail dispatcher. Tools themselves are
now plain functions or callable classes; no abstract base class is
required.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
  """Result of a tool execution.

  Attributes:
    success: Whether the tool executed successfully.
    result: The result data (string content or dict for structured results).
    error: Error message if success is False.
    content_metadata: Optional metadata for content display events.
      When provided, the agent emits a ToolContentEvent after ToolResultEvent.
      Contains operation, path, content_type, content, and metadata dict.
  """

  success: bool
  result: str | dict[str, Any] = ""
  error: str | None = None
  content_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValidationResult:
  """Result of a guardrail validation check.

  Attributes:
    valid: Whether the parameters passed validation.
    reason: Explanation if validation failed.
  """

  valid: bool
  reason: str | None = None


__all__ = ["ToolResult", "ValidationResult"]
