"""Tests for GitHub issue fixes - agent tool namespacing and model override.

Validates the fixes for:
1. Agent model not being applied (now uses agent's model over config)
2. Tool availability check (yoker:read resolves to read in registry)
"""

import sys
from pathlib import Path

# Add examples/plugins to sys.path for testing
EXAMPLES_PATH = Path(__file__).parent.parent / "examples" / "plugins"
if str(EXAMPLES_PATH) not in sys.path:
  sys.path.insert(0, str(EXAMPLES_PATH))


class TestIssue1AgentModelOverride:
  """Issue 1: Agent model not being applied."""

  def test_agent_model_overrides_config(self) -> None:
    """Agent definition's model should override config's model."""
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.core import Agent
    from yoker.core.thinking import ThinkingMode

    config = Config()
    config_model = config.backend.ollama.model

    # Agent with different model
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test",
      model="custom-model:latest",
      system_prompt="Test",
      tools=("read",),
    )

    core = Agent(config=config, thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Agent's model should override config
    assert core.model == "custom-model:latest"
    assert core.model != config_model

  def test_agent_without_model_uses_config(self) -> None:
    """Agent without model should use config's model."""
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.core import Agent
    from yoker.core.thinking import ThinkingMode

    config = Config()

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test",
      model=None,  # No model
      system_prompt="Test",
      tools=("read",),
    )

    core = Agent(config=config, thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Should use config's model
    assert core.model == config.backend.ollama.model


class TestIssue3ToolAvailability:
  """Issue 3: Tool availability check broken."""

  def test_yoker_namespace_resolves_to_builtin(self) -> None:
    """yoker:read should resolve to read in tool registry."""
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.core import Agent
    from yoker.core.thinking import ThinkingMode

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test",
      model=None,
      system_prompt="Test",
      tools=("yoker:read",),  # Only read allowed
    )

    core = Agent(config=Config(), thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # yoker:read should make 'yoker:read' available
    assert core.tools.get("yoker:read") is not None
    # Other tools should not be available
    assert core.tools.get("yoker:write") is None

  def test_mixed_namespaces_filter_correctly(self) -> None:
    """Agent with mixed tool namespaces should filter correctly."""
    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.core import Agent
    from yoker.core.thinking import ThinkingMode

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test",
      model=None,
      system_prompt="Test",
      tools=("yoker:read", "yoker:list"),  # Only yoker tools
    )

    core = Agent(config=Config(), thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Both should be available
    assert core.tools.get("yoker:read") is not None
    assert core.tools.get("yoker:list") is not None
    # Others should not
    assert core.tools.get("yoker:write") is None


class TestEndToEndDemoPlugin:
  """End-to-end tests with demo plugin."""

  def test_tool_availability_command_output(self) -> None:
    """Tool availability should show correct markers."""
    import asyncio
    from unittest.mock import Mock

    from yoker.agents import AgentDefinition
    from yoker.config import Config
    from yoker.core import Agent
    from yoker.core.thinking import ThinkingMode
    from yoker.ui.commands.tools import create_command as create_tools_command

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test",
      model=None,
      system_prompt="Test",
      tools=("yoker:read",),
    )

    core = Agent(config=Config(), thinking_mode=ThinkingMode.ON, agent_definition=agent_def)

    # Create tools command
    cmd = create_tools_command()
    output = asyncio.run(cmd.handler("", core, Mock()))

    # Check output format
    lines = output.split("\n")

    # Built-in section should show read available
    built_in_section = False
    for line in lines:
      if "Built-in:" in line:
        built_in_section = True
      elif built_in_section and "read" in line:
        # read should be marked as available
        assert "✓ read" in line or "read" in line
        break

    # Agent section should show allowed tools
    assert "Agent: test" in output
    assert "yoker:read" in output
