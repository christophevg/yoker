"""Tests for the /tools command."""

from typing import Any
from unittest.mock import Mock

from yoker.commands import create_tools_command
from yoker.tools import ToolRegistry
from yoker.tools.base import Tool


class MockTool(Tool):
  """Mock tool for testing."""

  @property
  def name(self) -> str:
    return "mock_tool"

  @property
  def description(self) -> str:
    return "A mock tool for testing"

  def get_schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {"type": "object", "properties": {}},
      },
    }

  async def execute(self, **kwargs: Any) -> str:
    return "mock result"


class TestToolsCommand:
  """Tests for create_tools_command."""

  def test_create_tools_command(self) -> None:
    """Test creating the tools command."""
    registry = ToolRegistry()

    # Create mock AgentCore
    agent_core = Mock()
    agent_core.get_known_tools.return_value = []
    agent_core.agent_definition = None

    command = create_tools_command(registry, agent_core)

    assert command.name == "tools"
    assert "tool" in command.description.lower()

  def test_tools_command_empty_registry(self) -> None:
    """Test tools command with empty registry."""
    registry = ToolRegistry()

    # Create mock AgentCore
    agent_core = Mock()
    agent_core.get_known_tools.return_value = []
    agent_core.agent_definition = None
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    assert "Known tools:" in result
    assert "Built-in:" in result

  def test_tools_command_with_known_tools(self) -> None:
    """Test tools command with known built-in tools."""
    registry = ToolRegistry()

    # Create mock AgentCore with known tools
    agent_core = Mock()
    mock_tool = Mock()
    mock_tool.name = "read"
    mock_tool.description = "Read file contents"
    agent_core.get_known_tools.return_value = [mock_tool]
    agent_core.agent_definition = None
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    assert "Known tools:" in result
    assert "Built-in:" in result
    assert "read" in result
    assert "Read file contents" in result

  def test_tools_command_with_available_tools(self) -> None:
    """Test tools command showing available built-in tools."""
    registry = ToolRegistry()

    # Create mock tool
    mock_tool = Mock()
    mock_tool.name = "read"
    mock_tool.description = "Read file contents"

    # Create mock AgentCore with known tool
    agent_core = Mock()
    agent_core.get_known_tools.return_value = [mock_tool]
    agent_core.agent_definition = None
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    # Built-in tools should be shown even if not in registry
    assert "Known tools:" in result
    assert "Built-in:" in result
    assert "read" in result
    assert "Read file contents" in result
    # Tool should be marked as not available (not in registry)
    assert "✗" in result

  def test_tools_command_with_agent_filtering(self) -> None:
    """Test tools command with agent filtering."""
    registry = ToolRegistry()
    registry.register(MockTool())

    # Create mock AgentCore with agent definition
    agent_core = Mock()
    agent_core.get_known_tools.return_value = []
    mock_agent_def = Mock()
    mock_agent_def.name = "test-agent"
    mock_agent_def.tools = ["read"]
    agent_core.agent_definition = mock_agent_def
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    assert "test-agent" in result
    assert "Allowed tools: read" in result

  def test_tools_command_ignores_args(self) -> None:
    """Test that tools command ignores any arguments passed."""
    registry = ToolRegistry()

    # Create mock AgentCore
    agent_core = Mock()
    agent_core.get_known_tools.return_value = []
    agent_core.agent_definition = None
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)

    result1 = command.handler([])
    result2 = command.handler(["some", "args"])

    # Both should return the same output
    assert result1 == result2

  def test_tools_command_with_plugin_tools_namespaced(self) -> None:
    """Test that plugin tools show namespaced names."""
    from yoker.plugins.registration import _clone_tool_with_name

    registry = ToolRegistry()

    # Create a plugin tool with namespace
    original_tool = MockTool()  # name="mock_tool"
    namespaced_tool = _clone_tool_with_name(original_tool, "demo:mock_tool")
    registry.register(namespaced_tool)

    # Create mock AgentCore with plugin tool
    agent_core = Mock()
    agent_core.get_known_tools.return_value = []
    agent_core.agent_definition = None
    agent_core.plugin_tools = [namespaced_tool]

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    # Plugin tools should show namespaced name
    assert "Known tools:" in result
    assert "Plugins:" in result
    assert "demo:mock_tool" in result
    # Should NOT show un-namespaced version
    assert "✗ mock_tool" not in result

  def test_tools_command_truncates_long_descriptions(self) -> None:
    """Test that long descriptions are truncated."""

    class LongDescTool(Tool):
      @property
      def name(self) -> str:
        return "long_desc_tool"

      @property
      def description(self) -> str:
        # Create a description that exceeds 60 chars (truncation threshold)
        return "This is a very long description that should be truncated because it exceeds the maximum length for display purposes"

      def get_schema(self) -> dict[str, Any]:
        return {
          "type": "function",
          "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}},
          },
        }

      async def execute(self, **kwargs: Any) -> str:
        return "result"

    long_tool = LongDescTool()
    registry = ToolRegistry()

    # Create mock AgentCore with the tool as a known built-in tool
    agent_core = Mock()
    agent_core.get_known_tools.return_value = [long_tool]
    agent_core.agent_definition = None
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    # Should not show the complete long description (it's 102 chars)
    # The truncated version should be 60 chars max (57 chars + "...")
    assert len(long_tool.description) > 60  # Verify description is indeed long
    # Check that truncated version is shown (ends with ...)
    assert "..." in result
    # Check that the description was truncated (partial description + ...)
    assert "This is a very long description that should be truncated ..." in result
    # Check that the full long description is NOT present (should be cut off)
    assert "display purposes" not in result

  def test_tools_command_skill_in_builtin(self) -> None:
    """Test that skill tool appears in Built-in section when enabled."""
    registry = ToolRegistry()

    # Create mock skill tool
    skill_tool = Mock()
    skill_tool.name = "skill"
    skill_tool.description = "Invoke a skill by name"

    # Create mock AgentCore with skill tool
    agent_core = Mock()
    agent_core.get_known_tools.return_value = [skill_tool]
    agent_core.agent_definition = None
    agent_core.plugin_tools = []

    command = create_tools_command(registry, agent_core)
    result = command.handler([])

    # Skill should appear in Built-in section
    assert "Known tools:" in result
    assert "Built-in:" in result
    assert "skill" in result
    assert "Invoke a skill by name" in result
    # Should NOT have a "Special" section
    assert "Special:" not in result
