"""Base types and abstract class for Yoker tools.

Provides the Tool abstract base class, result types, and validation types
that all concrete tools must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail


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
  result: str | dict[str, Any]
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


class Tool(ABC):
  """Abstract base class for all Yoker tools.

  Each tool must define its name, description, JSON schema for the LLM,
  and an execute method that returns a ToolResult.

  Tools may optionally accept a Guardrail instance for defense-in-depth
  validation. When a guardrail is provided, the tool validates parameters
  in execute() before performing any I/O.

  Example:
    class MyTool(Tool):
      @property
      def name(self) -> str:
        return "my_tool"

      @property
      def description(self) -> str:
        return "Does something useful"

      def get_schema(self) -> dict[str, Any]:
        return {
          "type": "function",
          "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {
              "type": "object",
              "properties": {
                "arg": {"type": "string"}
              },
              "required": ["arg"]
            }
          }
        }

      def execute(self, arg: str) -> ToolResult:
        return ToolResult(success=True, result=f"Got: {arg}")
  """

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize the tool with an optional guardrail.

    Args:
      guardrail: Optional guardrail for defense-in-depth validation.
    """
    self._guardrail = guardrail

  @property
  @abstractmethod
  def name(self) -> str:
    """Tool name used for registration and LLM tool calling."""

  @property
  @abstractmethod
  def description(self) -> str:
    """Tool description shown to the LLM."""

  @abstractmethod
  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible function schema.

    Returns:
      Dict in OpenAI function-calling format:
      {
        "type": "function",
        "function": {
          "name": "...",
          "description": "...",
          "parameters": {...}
        }
      }
    """

  @abstractmethod
  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute the tool with the given parameters.

    Args:
      **kwargs: Parameters from the LLM tool call.

    Returns:
      ToolResult with success status and output.
    """
