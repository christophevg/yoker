"""Tests for ToolRegistry."""

from typing import Annotated

import pytest

from yoker.tools import ToolRegistry
from yoker.tools.annotations import Text
from yoker.tools.schema import ToolResult


async def read_file(path: Annotated[str, Text("Path to read")]) -> str:
  """Read a file."""
  return f"contents of {path}"


class TestToolRegistry:
  """Tests for ToolRegistry."""

  def test_register_and_get(self) -> None:
    """Register a callable and retrieve its spec."""
    registry = ToolRegistry()
    spec = registry.register(read_file)
    assert registry.get("read_file") is spec

  def test_get_missing(self) -> None:
    """Get returns None for missing tools."""
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None

  def test_list_tools(self) -> None:
    """list_tools returns registered specs sorted by name."""
    registry = ToolRegistry()
    registry.register(read_file)
    tools = registry.tools
    assert len(tools) == 1
    assert tools[0].name == "read_file"

  def test_duplicate_registration(self) -> None:
    """Registering duplicate callable raises ValueError."""
    registry = ToolRegistry()
    registry.register(read_file)
    with pytest.raises(ValueError, match="already registered"):
      registry.register(read_file)

  def test_names(self) -> None:
    """names property returns sorted tool names."""
    registry = ToolRegistry()
    registry.register(read_file)
    assert registry.names == ["read_file"]

  def test_get_schemas(self) -> None:
    """get_schemas returns schemas for all tools."""
    registry = ToolRegistry()
    registry.register(read_file)
    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "read_file"

  def test_namespace_registration(self) -> None:
    """Registering with a namespace prefixes the tool name."""
    registry = ToolRegistry()
    spec = registry.register(read_file, namespace="pkgq")
    assert spec.name == "pkgq:read_file"
    assert registry.get("pkgq:read_file") is spec

  def test_multiple_tools_sorted(self) -> None:
    """Multiple tools are returned sorted by name."""

    async def alpha() -> ToolResult:
      """Alpha tool."""
      return ToolResult(success=True, result="")

    async def zeta() -> ToolResult:
      """Zeta tool."""
      return ToolResult(success=True, result="")

    registry = ToolRegistry()
    registry.register(zeta)
    registry.register(alpha)
    names = registry.names
    assert names == ["alpha", "zeta"]

  def test_explicit_name_override(self) -> None:
    """An explicit name override can be provided."""
    registry = ToolRegistry()
    spec = registry.register(read_file, name="custom_read")
    assert spec.name == "custom_read"
    assert registry.get("custom_read") is spec
