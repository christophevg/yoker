"""Tests for the /agents command."""

from unittest.mock import Mock

import pytest

from yoker.agents import AgentDefinition, AgentRegistry
from yoker.ui.commands.agents import create_command as create_agents_command


class TestAgentsCommand:
  """Tests for create_agents_command."""

  def _make_agent(self, agent_def, directories=(), plugin_agents=()):
    agent = Mock()
    agent.definition = agent_def
    agent.agent_definition = agent_def
    agent.config.agents.directories = directories
    # agent.agents is removed; the registry lives on the
    # session. The command reads agent._session.agents.
    registry = AgentRegistry()
    for d in plugin_agents:
      registry.register(d)
    session = Mock()
    session.agents = registry
    agent._session = session
    return agent

  @pytest.mark.asyncio
  async def test_create_agents_command(self) -> None:
    """Test creating the agents command."""
    command = create_agents_command()
    assert command.name == "agents"
    assert "agent" in command.description.lower()

  @pytest.mark.asyncio
  async def test_agents_command_with_agent(self) -> None:
    """Test agents command when an agent is loaded."""
    agent_def = AgentDefinition(
      simple_name="test-agent",
      description="A test agent",
      model="gemini-3-flash-preview:cloud",
      tools=["read", "write"],
    )

    agent = self._make_agent(agent_def=agent_def)
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Current agent:" in result
    assert "test-agent" in result
    assert "A test agent" in result
    assert "gemini-3-flash-preview:cloud" in result
    assert "read, write" in result

  @pytest.mark.asyncio
  async def test_agents_command_without_model(self) -> None:
    """Test agents command when agent has no model specified."""
    agent_def = AgentDefinition(
      simple_name="simple-agent",
      description="A simple agent",
      tools=(),
    )

    agent = self._make_agent(agent_def=agent_def)
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Current agent:" in result
    assert "simple-agent" in result
    assert "A simple agent" in result
    # Model line should not appear when model is None
    assert "      Model:" not in result

  @pytest.mark.asyncio
  async def test_agents_command_without_tools(self) -> None:
    """Test agents command when agent has no tools specified."""
    agent_def = AgentDefinition(
      simple_name="no-tools-agent",
      description="An agent without tools",
      tools=(),
      model="gemini-3-flash-preview:cloud",
    )

    agent = self._make_agent(agent_def=agent_def)
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Current agent:" in result
    assert "no-tools-agent" in result
    # Tools line should not appear when tools is empty
    assert "      Tools:" not in result

  @pytest.mark.asyncio
  async def test_agents_command_ignores_args(self) -> None:
    """Test that agents command ignores any arguments passed."""
    agent_def = AgentDefinition(
      simple_name="test-agent",
      description="A test agent",
      tools=(),
    )

    agent = self._make_agent(agent_def=agent_def)
    command = create_agents_command()

    result1 = await command.handler("", agent, Mock())
    result2 = await command.handler("some args", agent, Mock())

    # Both should return the same output
    assert result1 == result2

  @pytest.mark.asyncio
  async def test_agents_command_lists_known_agents(self) -> None:
    """Test that known agents from the session registry are listed."""
    current_def = AgentDefinition(
      simple_name="current-agent",
      description="The active agent",
      tools=(),
    )
    other_def = AgentDefinition(
      simple_name="researcher",
      description="A research agent",
      tools=("read", "search"),
    )

    agent = self._make_agent(
      agent_def=current_def,
      plugin_agents=[current_def, other_def],
    )
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Known agents:" in result
    assert "No agents configured." not in result
    assert "current-agent" in result
    assert "researcher" in result
    assert "A research agent" in result

  @pytest.mark.asyncio
  async def test_agents_command_no_known_agents_without_session(self) -> None:
    """Test that known agents shows 'No agents configured' when no session."""
    agent_def = AgentDefinition(
      simple_name="standalone-agent",
      description="A standalone agent",
      tools=(),
    )

    agent = Mock()
    agent.definition = agent_def
    # Mock auto-creates attributes; explicitly set _session to None to
    # simulate a standalone Agent without a Session.
    agent._session = None
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Known agents:" in result
    assert "No agents configured." in result
