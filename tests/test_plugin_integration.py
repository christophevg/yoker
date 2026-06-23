"""Integration tests for plugin system with skill commands."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from yoker.agent import Agent
from yoker.config import Config, PluginsConfig
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.tools import create_command as create_tools_command


@pytest.fixture
def demo_plugin_config():
  """Create configuration for demo plugin testing."""
  return Config(
    plugins=PluginsConfig(
      enabled=True,
      trusted={"yoker_plugin_demo": True},
    )
  )


@pytest.fixture
def agent_with_demo_plugin(demo_plugin_config):
  """Create agent with demo plugin loaded."""
  return Agent(config=demo_plugin_config, plugins=["yoker_plugin_demo"])


class TestPluginSkillCommands:
  """Test that plugin skills are invoked dynamically."""

  def test_plugin_skill_is_registered(self, agent_with_demo_plugin):
    """Plugin skill should be registered in skill registry."""
    assert agent_with_demo_plugin.skills is not None
    assert len(agent_with_demo_plugin.skills) == 1

    skills = agent_with_demo_plugin.skills.skills
    assert len(skills) == 1
    skill = skills[0]
    assert skill.name == "yoker_plugin_demo:greeting"
    assert skill.namespace == "yoker_plugin_demo"

  @pytest.mark.asyncio
  async def test_plugin_skill_dynamic_dispatch(self, agent_with_demo_plugin):
    """Plugin skill should be dispatchable dynamically."""
    registry = create_default_registry()
    agent = agent_with_demo_plugin

    with (
      patch.object(agent, "inject_skill_context") as mock_inject,
      patch.object(agent, "process", new_callable=AsyncMock) as mock_process,
    ):
      result = await registry.dispatch(
        "/yoker_plugin_demo:greeting",
        agent,
        Mock(),
      )

    assert result is None
    mock_inject.assert_called_once_with("yoker_plugin_demo:greeting", "")
    mock_process.assert_awaited_once_with("Execute the skill as requested.")

  @pytest.mark.asyncio
  async def test_plugin_skill_dynamic_dispatch_with_args(self, agent_with_demo_plugin):
    """Plugin skill dispatch forwards arguments."""
    registry = create_default_registry()
    agent = agent_with_demo_plugin

    with (
      patch.object(agent, "inject_skill_context") as mock_inject,
      patch.object(agent, "process", new_callable=AsyncMock) as mock_process,
    ):
      result = await registry.dispatch(
        "/yoker_plugin_demo:greeting hello world",
        agent,
        Mock(),
      )

    assert result is None
    mock_inject.assert_called_once_with("yoker_plugin_demo:greeting", "hello world")
    mock_process.assert_awaited_once_with("hello world")

  @pytest.mark.asyncio
  async def test_full_command_registry_flow(self, agent_with_demo_plugin, demo_plugin_config):
    """Test the complete UI-layer command registry flow."""
    registry = create_default_registry()

    command_names = registry.names

    # Built-in commands
    assert "help" in command_names
    assert "skills" in command_names
    assert "think" in command_names
    assert "context" in command_names

    # Plugin skill is not registered as an explicit command; it is invoked
    # dynamically via the skill registry.
    assert "yoker_plugin_demo:greeting" not in command_names

    from yoker.ui import BatchUIHandler

    ui = BatchUIHandler()

    # Test dispatch
    help_result = await registry.dispatch("/help", agent_with_demo_plugin, ui)
    assert help_result is not None

    skills_result = await registry.dispatch("/skills", agent_with_demo_plugin, ui)
    assert skills_result is not None
    assert "yoker_plugin_demo:greeting" in skills_result

    # Test dynamic skill invocation
    with (
      patch.object(agent_with_demo_plugin, "inject_skill_context") as mock_inject,
      patch.object(agent_with_demo_plugin, "process", new_callable=AsyncMock) as mock_process,
    ):
      result = await registry.dispatch(
        "/yoker_plugin_demo:greeting hello",
        agent_with_demo_plugin,
        ui,
      )

    assert result is None
    mock_inject.assert_called_once_with("yoker_plugin_demo:greeting", "hello")
    mock_process.assert_awaited_once_with("hello")

  @pytest.mark.asyncio
  async def test_plugin_tool_namespace_in_tools_command(self, agent_with_demo_plugin):
    """Plugin tools should show namespaced names in /tools command."""
    agent = agent_with_demo_plugin
    command = create_tools_command()

    # Dispatch command
    result = await command.handler("", agent, Mock())

    # Plugin tool should show namespaced name
    assert "yoker_plugin_demo:echo" in result
    # Should NOT show un-namespaced version
    assert "✗ echo " not in result  # Un-namespaced would be "✗ echo "

  @pytest.mark.asyncio
  async def test_tools_command_case_insensitive_builtin_tools(self):
    """/tools marks built-in tools available even with uppercase names."""
    from yoker.agent import Agent
    from yoker.agents import AgentDefinition
    from yoker.config import Config

    agent_def = AgentDefinition(
      simple_name="test",
      description="Test",
      tools=("Read", "List", "WRITE"),
      system_prompt="Test",
    )
    agent = Agent(config=Config(), agent_definition=agent_def)
    command = create_tools_command()

    result = await command.handler("", agent, Mock())

    # Tools are displayed with yoker: namespace prefix
    assert "✓ yoker:read" in result
    assert "✓ yoker:list" in result
    assert "✓ yoker:write" in result
