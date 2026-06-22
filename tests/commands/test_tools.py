"""Tests for the /tools command."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from yoker.tools import ToolRegistry
from yoker.ui.commands.tools import create_command as create_tools_command


def _tool_meta(name: str, description: str) -> Any:
  """Create a lightweight tool metadata object for the command handler."""
  return SimpleNamespace(name=name, description=description)


class TestToolsCommand:
  """Tests for create_tools_command."""

  def _make_agent(
    self, known_tools=(), plugin_tools=(), agent_definition=None, registry_names=None
  ):
    agent = Mock()
    agent.agent_definition = agent_definition
    agent.plugin_tools = list(plugin_tools)
    agent.get_known_tools.return_value = list(known_tools)

    registry = Mock()
    registry.names = list(registry_names) if registry_names is not None else []
    registry.get.return_value = None
    agent.tool_registry = registry
    return agent, registry

  @pytest.mark.asyncio
  async def test_create_tools_command(self) -> None:
    """Test creating the tools command."""
    agent, _ = self._make_agent()
    command = create_tools_command()

    assert command.name == "tools"
    assert "tool" in command.description.lower()

  @pytest.mark.asyncio
  async def test_tools_command_empty_registry(self) -> None:
    """Test tools command with empty registry."""
    agent, _ = self._make_agent()
    command = create_tools_command()
    result = await command.handler("", agent, Mock())

    assert "Known tools:" in result
    assert "Built-in:" in result

  @pytest.mark.asyncio
  async def test_tools_command_with_known_tools(self) -> None:
    """Test tools command with known built-in tools."""
    read_meta = _tool_meta("read", "Read file contents")
    agent, registry = self._make_agent(known_tools=[read_meta], registry_names=["read"])
    registry.get.side_effect = lambda name: read_meta if name == "read" else None

    command = create_tools_command()
    result = await command.handler("", agent, Mock())

    assert "Known tools:" in result
    assert "Built-in:" in result
    assert "read" in result
    assert "Read file contents" in result

  @pytest.mark.asyncio
  async def test_tools_command_with_available_tools(self) -> None:
    """Test tools command showing availability markers."""
    read_meta = _tool_meta("read", "Read file contents")

    agent, _ = self._make_agent(known_tools=[read_meta], registry_names=[])

    command = create_tools_command()
    result = await command.handler("", agent, Mock())

    # Known but not available should be marked with ✗
    assert "Known tools:" in result
    assert "Built-in:" in result
    assert "✗ read" in result

  @pytest.mark.asyncio
  async def test_tools_command_with_agent_filtering(self) -> None:
    """Test tools command with agent filtering."""
    from yoker.builtin import read

    registry = ToolRegistry()
    registry.register(read)

    read_meta = _tool_meta("read", "Read file contents")

    mock_agent_def = Mock()
    mock_agent_def.name = "test-agent"
    mock_agent_def.tools = ["read"]

    agent, _ = self._make_agent(
      known_tools=[read_meta],
      agent_definition=mock_agent_def,
      registry_names=["read"],
    )

    command = create_tools_command()
    result = await command.handler("", agent, Mock())

    assert "test-agent" in result
    assert "Allowed tools: read" in result

  @pytest.mark.asyncio
  async def test_tools_command_ignores_args(self) -> None:
    """Test that tools command ignores any arguments passed."""
    agent, _ = self._make_agent()
    command = create_tools_command()

    result1 = await command.handler("", agent, Mock())
    result2 = await command.handler("some args", agent, Mock())

    # Both should return the same output
    assert result1 == result2

  @pytest.mark.asyncio
  async def test_tools_command_with_plugin_tools_namespaced(self) -> None:
    """Test that plugin tools show namespaced names."""
    plugin_meta = _tool_meta("demo:mock_tool", "A plugin tool for testing")

    agent, registry = self._make_agent(
      plugin_tools=[plugin_meta],
      registry_names=["demo:mock_tool"],
    )
    registry.get.side_effect = lambda name: plugin_meta if name == "demo:mock_tool" else None

    command = create_tools_command()
    result = await command.handler("", agent, Mock())

    # Plugin tools should show namespaced name
    assert "Known tools:" in result
    assert "Plugins:" in result
    assert "demo:mock_tool" in result
    # Should NOT show un-namespaced version
    assert "✗ mock_tool" not in result

  @pytest.mark.asyncio
  async def test_tools_command_truncates_long_descriptions(self) -> None:
    """Test that long descriptions are truncated."""
    long_desc = (
      "This is a very long description that should be truncated "
      "because it exceeds the maximum length for display purposes"
    )
    long_meta = _tool_meta("long_desc_tool", long_desc)
    agent, _ = self._make_agent(known_tools=[long_meta], registry_names=["long_desc_tool"])

    command = create_tools_command()
    result = await command.handler("", agent, Mock())

    # Should not show the complete long description (it's 102 chars)
    assert len(long_desc) > 60  # Verify description is indeed long
    # Check that truncated version is shown (ends with ...)
    assert "..." in result
    # Check that the description was truncated
    assert "This is a very long description that should be truncated ..." in result
    # Check that the full long description is NOT present (should be cut off)
    assert "display purposes" not in result
