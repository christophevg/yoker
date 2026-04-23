"""Base types and abstract class for Yoker tools.

Provides the Tool abstract base class, result types, and validation types
that all concrete tools must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
  """Result of a tool execution.

  Attributes:
    success: Whether the tool executed successfully.
    result: The result string (content on success, empty on failure).
    error: Error message if success is False.
  """

  success: bool
  result: str
  error: str | None = None


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
