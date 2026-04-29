"""Tools package for Yoker.

Provides the tool framework including base classes, registry, guardrails,
and concrete tool implementations.
"""

from typing import TYPE_CHECKING

from .base import Tool, ToolResult, ValidationResult
from .existence import ExistenceTool
from .guardrails import Guardrail
from .list import ListTool
from .path_guardrail import PathGuardrail
from .read import ReadTool
from .registry import ToolRegistry
from .search import SearchTool
from .update import UpdateTool
from .write import WriteTool

if TYPE_CHECKING:
  from yoker.agent import Agent


def create_default_registry(parent_agent: "Agent | None" = None) -> ToolRegistry:
  """Create a registry with all built-in tools registered.

  Args:
    parent_agent: Optional parent agent for AgentTool (required for subagent spawning).

  Returns:
    ToolRegistry with default tools (read, list, write, update, search, existence, agent).
  """
  from .agent import AgentTool

  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(WriteTool())
  registry.register(UpdateTool())
  registry.register(SearchTool())
  registry.register(ExistenceTool())
  registry.register(AgentTool(parent_agent=parent_agent))
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
  "ListTool",
  "WriteTool",
  "UpdateTool",
  "SearchTool",
  "ExistenceTool",
  "AgentTool",
  "AVAILABLE_TOOLS",
  "create_default_registry",
]
