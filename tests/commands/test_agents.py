"""Tests for the /agents command."""

from unittest.mock import Mock

from yoker.agents import AgentDefinition
from yoker.commands import create_agents_command


class TestAgentsCommand:
  """Tests for create_agents_command."""

  def test_create_agents_command(self) -> None:
    """Test creating the agents command."""

    def get_agent() -> AgentDefinition | None:
      return None

    # Create mock config with no agents directory
    config = Mock()
    config.agents.directory = ""

    command = create_agents_command(get_agent, config)

    assert command.name == "agents"
    assert "agent" in command.description.lower()

  def test_agents_command_no_agent_loaded(self) -> None:
    """Test agents command when no agent is loaded."""

    def get_agent() -> AgentDefinition | None:
      return None

    # Create mock config with no agents directory
    config = Mock()
    config.agents.directory = ""

    command = create_agents_command(get_agent, config)
    result = command.handler([])

    assert "Current agent:" in result
    assert "(default)" in result
    assert "No agent definition loaded" in result

  def test_agents_command_with_agent(self) -> None:
    """Test agents command when an agent is loaded."""
    agent_def = AgentDefinition(
      name="test-agent",
      description="A test agent",
      model="llama3.2:latest",
      tools=["read", "write"],
    )

    def get_agent() -> AgentDefinition | None:
      return agent_def

    # Create mock config
    config = Mock()
    config.agents.directory = ""

    command = create_agents_command(get_agent, config)
    result = command.handler([])

    assert "Current agent:" in result
    assert "test-agent" in result
    assert "A test agent" in result
    assert "llama3.2:latest" in result
    assert "read, write" in result

  def test_agents_command_without_model(self) -> None:
    """Test agents command when agent has no model specified."""
    agent_def = AgentDefinition(
      name="simple-agent",
      description="A simple agent",
      tools=(),
    )

    def get_agent() -> AgentDefinition | None:
      return agent_def

    # Create mock config
    config = Mock()
    config.agents.directory = ""

    command = create_agents_command(get_agent, config)
    result = command.handler([])

    assert "Current agent:" in result
    assert "simple-agent" in result
    assert "A simple agent" in result
    # Model line should not appear when model is None
    assert "Model:" not in result

  def test_agents_command_without_tools(self) -> None:
    """Test agents command when agent has no tools specified."""
    agent_def = AgentDefinition(
      name="no-tools-agent",
      description="An agent without tools",
      tools=(),
      model="llama3.2:latest",
    )

    def get_agent() -> AgentDefinition | None:
      return agent_def

    # Create mock config
    config = Mock()
    config.agents.directory = ""

    command = create_agents_command(get_agent, config)
    result = command.handler([])

    assert "Current agent:" in result
    assert "no-tools-agent" in result
    # Tools line should not appear when tools is None or empty
    assert "Tools:" not in result

  def test_agents_command_ignores_args(self) -> None:
    """Test that agents command ignores any arguments passed."""
    agent_def = AgentDefinition(
      name="test-agent",
      description="A test agent",
      tools=(),
    )

    def get_agent() -> AgentDefinition | None:
      return agent_def

    # Create mock config
    config = Mock()
    config.agents.directory = ""

    command = create_agents_command(get_agent, config)

    result1 = command.handler([])
    result2 = command.handler(["some", "args"])

    # Both should return the same output
    assert result1 == result2
