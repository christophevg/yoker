"""Tests for agent definition loading from files and plugins."""

import tempfile
from pathlib import Path

import pytest

from yoker.agent import Agent
from yoker.agent.agent import _load_agent_from_plugin_url


class TestAgentDefinitionFileValidation:
  """Test validation of agent definition files."""

  def test_invalid_file_path_raises_error(self):
    """Test that invalid file path raises ValueError."""
    with pytest.raises(ValueError, match="Agent definition file not found"):
      Agent(agent_path="/nonexistent/path/to/agent.md")

  def test_valid_file_path_loads_successfully(self):
    """Test that valid file path loads successfully."""
    # Use existing example agent
    agent_path = Path("examples/agents/markdown.md")
    if agent_path.exists():
      agent = Agent(agent_path=agent_path)
      assert agent.agent_definition is not None
      assert agent.agent_definition.name == "markdown"
    else:
      pytest.skip("Example agent file not found")

  def test_config_definition_validates_file_exists(self):
    """Test that config.agents.definition validates file existence."""
    from yoker.config import AgentsConfig, Config

    # Create a temp file for testing with valid frontmatter
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
      f.write(
        "---\nname: test\ndescription: Test agent\ntools:\n  - read\n---\nTest system prompt\n"
      )
      f.flush()
      temp_path = f.name

    try:
      # Valid file should work
      config = Config(agents=AgentsConfig(definition=temp_path))
      agent = Agent(config=config)
      assert agent.agent_definition is not None
      assert agent.agent_definition.name == "test"
    finally:
      Path(temp_path).unlink()

  def test_config_definition_invalid_file_raises_error(self):
    """Test that invalid config.agents.definition raises ValueError."""
    from yoker.config import AgentsConfig, Config

    config = Config(agents=AgentsConfig(definition="/nonexistent/agent.md"))

    with pytest.raises(ValueError, match="Agent definition file not found"):
      Agent(config=config)


class TestPluginURLAgentLoading:
  """Test loading agents from plugin:// URLs."""

  def test_invalid_plugin_url_format(self):
    """Test that invalid plugin URL format raises ValueError."""
    with pytest.raises(ValueError, match="Invalid plugin URL"):
      _load_agent_from_plugin_url("invalid://test")

  def test_plugin_url_missing_package(self):
    """Test that missing package raises ValueError."""
    with pytest.raises(ValueError, match="Plugin package not found"):
      _load_agent_from_plugin_url("plugin://nonexistent_package/agents/test")

  def test_plugin_url_format_validation(self):
    """Test plugin URL format validation."""
    # Missing agents component
    with pytest.raises(ValueError, match="Invalid plugin URL format"):
      _load_agent_from_plugin_url("plugin://package/wrong/test")

    # Missing agent name
    with pytest.raises(ValueError, match="Invalid plugin URL format"):
      _load_agent_from_plugin_url("plugin://package/agents")

    # Missing all components
    with pytest.raises(ValueError, match="Invalid plugin URL format"):
      _load_agent_from_plugin_url("plugin://package")

  def test_plugin_url_integration(self):
    """Test loading agent from plugin URL in Agent constructor."""
    # Test loading agent from plugin URL (yoker_plugin_demo)
    # Note: yoker_plugin_demo must be installed for this test to pass
    try:
      agent = Agent(agent_path="plugin://yoker_plugin_demo/agents/demo")
      assert agent.agent_definition is not None
      assert agent.agent_definition.name == "yoker_plugin_demo:demo"
      assert "yoker_plugin_demo:echo" in agent.agent_definition.tools
    except ImportError:
      pytest.skip("yoker_plugin_demo plugin not installed")


class TestAgentDefinitionLoading:
  """Test general agent definition loading behavior."""

  def test_agent_path_and_definition_both_provided(self):
    """Test that agent_definition takes precedence when both are provided."""
    from yoker.agents import AgentDefinition

    # Create a valid agent definition
    agent_def = AgentDefinition(
      name="test",
      description="Test agent",
      tools=("read",),
      system_prompt="Test prompt",
    )

    # When both provided, agent_definition should take precedence
    # agent_path should be ignored (not even validated)
    agent = Agent(agent_definition=agent_def, agent_path="/nonexistent/path.md")

    # agent_definition should be used, not agent_path
    assert agent.agent_definition is not None
    assert agent.agent_definition.name == "test"
