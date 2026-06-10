"""Integration tests for plugin system with skill commands."""

import pytest

from yoker.agent import Agent
from yoker.commands import CommandRegistry, create_skill_commands
from yoker.config import Config, PluginsConfig


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
  """Test that plugin skills are registered as commands."""

  def test_plugin_skill_is_registered(self, agent_with_demo_plugin):
    """Plugin skill should be registered in skill registry."""
    assert agent_with_demo_plugin.skill_registry is not None
    assert agent_with_demo_plugin.skill_registry.count == 1

    skills = list(agent_with_demo_plugin.skill_registry)
    assert len(skills) == 1
    skill_name, skill = skills[0]
    assert skill_name == "yoker_plugin_demo:greeting"
    assert skill.name == "greeting"
    assert skill.namespace == "yoker_plugin_demo"

  def test_plugin_skill_command_creation(self, agent_with_demo_plugin):
    """Plugin skill should create a command."""
    skill_registry = agent_with_demo_plugin.skill_registry
    assert skill_registry is not None

    commands = create_skill_commands(
      registry=skill_registry,
      get_skill_registry=lambda: skill_registry,
    )

    assert len(commands) == 1
    assert commands[0].name == "yoker_plugin_demo:greeting"
    assert "greeting" in commands[0].description.lower()

  def test_plugin_skill_command_dispatch(self, agent_with_demo_plugin, demo_plugin_config):
    """Plugin skill command should be dispatchable."""
    # Create command registry (simulating __main__.py flow)
    registry = CommandRegistry()

    # Register skill commands
    skill_registry = agent_with_demo_plugin.skill_registry
    assert skill_registry is not None

    skill_commands = create_skill_commands(
      registry=skill_registry,
      get_skill_registry=lambda: skill_registry,
    )

    for command in skill_commands:
      registry.register(command)

    # Dispatch the skill command
    result = registry.dispatch("/yoker_plugin_demo:greeting")

    # Should return skill injection marker
    assert result is not None
    assert result.startswith("__SKILL_INJECTION__")
    assert "yoker_plugin_demo:greeting" in result

  def test_full_command_registry_flow(self, agent_with_demo_plugin, demo_plugin_config):
    """Test the complete flow as it happens in __main__.py."""
    from yoker.__main__ import create_command_registry

    # This simulates what happens in __main__.py
    registry = create_command_registry(agent_with_demo_plugin, demo_plugin_config)

    # Should have both built-in and skill commands
    command_names = registry.names

    # Built-in commands
    assert "help" in command_names
    assert "skills" in command_names
    assert "think" in command_names
    assert "context" in command_names

    # Plugin skill command
    assert "yoker_plugin_demo:greeting" in command_names

    # Test dispatch
    help_result = registry.dispatch("/help")
    assert help_result is not None
    assert "yoker_plugin_demo:greeting" in help_result

    skills_result = registry.dispatch("/skills")
    assert skills_result is not None
    assert "yoker_plugin_demo:greeting" in skills_result

    skill_result = registry.dispatch("/yoker_plugin_demo:greeting")
    assert skill_result is not None
    assert skill_result.startswith("__SKILL_INJECTION__")

  def test_plugin_tool_namespace_in_tools_command(self, agent_with_demo_plugin):
    """Plugin tools should show namespaced names in /tools command."""
    from yoker.commands import create_tools_command

    # Create tools command
    tools_cmd = create_tools_command(
      registry=agent_with_demo_plugin.tool_registry,
      agent_core=agent_with_demo_plugin._core,
    )

    # Dispatch command
    result = tools_cmd.handler([])

    # Plugin tool should show namespaced name
    assert "yoker_plugin_demo:echo" in result
    # Should NOT show un-namespaced version
    assert "✗ echo " not in result  # Un-namespaced would be "✗ echo "
