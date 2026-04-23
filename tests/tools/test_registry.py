"""Tests for ToolRegistry."""

import pytest

from yoker.tools import ReadTool, ToolRegistry
from yoker.tools.base import Tool, ToolResult


class TestToolRegistry:
  """Tests for ToolRegistry."""

  def test_register_and_get(self) -> None:
    """Register a tool and retrieve it."""
    registry = ToolRegistry()
    tool = ReadTool()
    registry.register(tool)
    assert registry.get("read") is tool

  def test_get_missing(self) -> None:
    """Get returns None for missing tools."""
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None

  def test_list_tools(self) -> None:
    """list_tools returns registered tools sorted by name."""
    registry = ToolRegistry()
    registry.register(ReadTool())
    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "read"

  def test_duplicate_registration(self) -> None:
    """Registering duplicate tool raises ValueError."""
    registry = ToolRegistry()
    registry.register(ReadTool())
    with pytest.raises(ValueError, match="already registered"):
      registry.register(ReadTool())

  def test_names(self) -> None:
    """names property returns sorted tool names."""
    registry = ToolRegistry()
    registry.register(ReadTool())
    assert registry.names == ["read"]

  def test_get_schemas(self) -> None:
    """get_schemas returns schemas for all tools."""
    registry = ToolRegistry()
    registry.register(ReadTool())
    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "read"

  def test_multiple_tools_sorted(self) -> None:
    """Multiple tools are returned sorted by name."""

    class AlphaTool(Tool):
      @property
      def name(self) -> str:
        return "alpha"

      @property
      def description(self) -> str:
        return "Alpha tool"

      def get_schema(self) -> dict:
        return {"type": "function", "function": {"name": "alpha"}}

      def execute(self) -> ToolResult:
        return ToolResult(success=True, result="")

    class ZetaTool(Tool):
      @property
      def name(self) -> str:
        return "zeta"

      @property
      def description(self) -> str:
        return "Zeta tool"

      def get_schema(self) -> dict:
        return {"type": "function", "function": {"name": "zeta"}}

      def execute(self) -> ToolResult:
        return ToolResult(success=True, result="")

    registry = ToolRegistry()
    registry.register(ZetaTool())
    registry.register(AlphaTool())
    names = registry.names
    assert names == ["alpha", "zeta"]
