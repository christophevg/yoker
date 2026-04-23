"""Tool registry for managing and dispatching Yoker tools.

Provides ToolRegistry for registering, listing, and looking up tools by name.
Follows the same pattern as CommandRegistry in yoker.commands.
"""

from typing import Any

from .base import Tool


class ToolRegistry:
  """Registry for managing available tools.

  Tools are registered by name and can be retrieved for execution
  or schema generation for the LLM.

  Attributes:
    _tools: Internal dictionary mapping tool names to Tool instances.

  Example:
    registry = ToolRegistry()
    registry.register(ReadTool())
    tool = registry.get("read")
    schemas = registry.get_schemas()
  """

  def __init__(self) -> None:
    """Initialize an empty tool registry."""
    self._tools: dict[str, Tool] = {}

  def register(self, tool: Tool) -> None:
    """Register a tool.

    Args:
      tool: The Tool instance to register.

    Raises:
      ValueError: If a tool with the same name is already registered.
    """
    if tool.name in self._tools:
      raise ValueError(f"Tool '{tool.name}' is already registered")
    self._tools[tool.name] = tool

  def get(self, name: str) -> Tool | None:
    """Get a tool by name.

    Args:
      name: Tool name (case-sensitive).

    Returns:
      The Tool instance if found, None otherwise.
    """
    return self._tools.get(name)

  def list_tools(self) -> list[Tool]:
    """Get all registered tools.

    Returns:
      List of Tool instances sorted by name.
    """
    return sorted(self._tools.values(), key=lambda t: t.name)

  def get_schemas(self) -> list[dict[str, Any]]:
    """Get schemas for all registered tools.

    Returns:
      List of Ollama-compatible function schemas.
    """
    return [tool.get_schema() for tool in self.list_tools()]

  @property
  def names(self) -> list[str]:
    """Get all registered tool names.

    Returns:
      List of tool names sorted alphabetically.
    """
    return sorted(self._tools.keys())
