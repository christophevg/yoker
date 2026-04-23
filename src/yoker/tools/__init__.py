"""Tools package for Yoker.

Provides the tool framework including base classes, registry, guardrails,
and concrete tool implementations.
"""

from .base import Tool, ToolResult, ValidationResult
from .guardrails import Guardrail
from .path_guardrail import PathGuardrail
from .read import ReadTool
from .registry import ToolRegistry


def create_default_registry() -> ToolRegistry:
  """Create a registry with all built-in tools registered.

  Returns:
    ToolRegistry with default tools (read, list, write, update, search, agent).
  """
  registry = ToolRegistry()
  registry.register(ReadTool())
  return registry


# Default registry instance for backwards compatibility
AVAILABLE_TOOLS = create_default_registry()

__all__ = [
  "Tool",
  "ToolResult",
  "ValidationResult",
  "Guardrail",
  "PathGuardrail",
  "ToolRegistry",
  "ReadTool",
  "AVAILABLE_TOOLS",
  "create_default_registry",
]
