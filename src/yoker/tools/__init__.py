"""Tools package for Yoker.

Provides the tool framework including base classes, registry, guardrails,
and concrete tool implementations.
"""

from typing import TYPE_CHECKING

from .base import Tool, ToolResult, ValidationResult
from .existence import ExistenceTool
from .git import GitTool
from .guardrails import Guardrail
from .list import ListTool
from .mkdir import MkdirTool
from .path_guardrail import PathGuardrail
from .read import ReadTool
from .registry import ToolRegistry
from .search import SearchTool
from .update import UpdateTool
from .web_backend import (
  OllamaWebFetchBackend,
  OllamaWebSearchBackend,
  WebFetchBackend,
  WebSearchBackend,
)
from .web_guardrail import WebGuardrail, WebGuardrailConfig
from .web_types import FetchedContent, SearchResult, WebFetchError, WebSearchError
from .webfetch import WebFetchTool
from .websearch import WebSearchTool
from .write import WriteTool

if TYPE_CHECKING:
  from yoker.agent import Agent


def create_default_registry(parent_agent: "Agent | None" = None) -> ToolRegistry:
  """Create a registry with all built-in tools registered.

  Args:
    parent_agent: Optional parent agent for AgentTool (required for subagent spawning).

  Returns:
    ToolRegistry with default tools (read, list, write, update, search, existence, mkdir, git, agent).
  """
  from .agent import AgentTool

  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(WriteTool())
  registry.register(UpdateTool())
  registry.register(SearchTool())
  registry.register(ExistenceTool())
  registry.register(MkdirTool())
  registry.register(AgentTool(parent_agent=parent_agent))
  # GitTool requires config - added separately when config is available
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
  "MkdirTool",
  "GitTool",
  "AgentTool",
  "WebSearchTool",
  "WebSearchBackend",
  "OllamaWebSearchBackend",
  "WebFetchTool",
  "WebFetchBackend",
  "OllamaWebFetchBackend",
  "WebGuardrail",
  "WebGuardrailConfig",
  "SearchResult",
  "WebSearchError",
  "FetchedContent",
  "WebFetchError",
  "AVAILABLE_TOOLS",
  "create_default_registry",
]
