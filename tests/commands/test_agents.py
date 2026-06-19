"""Tests for the /agents command."""

from unittest.mock import Mock

import pytest

from yoker.agents import AgentDefinition
from yoker.ui.commands.agents import create_command as create_agents_command


class TestAgentsCommand:
  """Tests for create_agents_command."""

  def _make_agent(self, agent_def=None, directories=(), plugin_agents=()):
    agent = Mock()
    agent.agent_definition = agent_def
    agent.config.agents.directories = directories
    agent.plugin_agents = plugin_agents
    return agent

  @pytest.mark.asyncio
  async def test_create_agents_command(self) -> None:
    """Test creating the agents command."""
    command = create_agents_command()
    assert command.name == "agents"
    assert "agent" in command.description.lower()

  @pytest.mark.asyncio
  async def test_agents_command_no_agent_loaded(self) -> None:
    """Test agents command when no agent is loaded."""
    agent = self._make_agent()
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Current agent:" in result
    assert "(default)" in result
    assert "No agent definition loaded" in result

  @pytest.mark.asyncio
  async def test_agents_command_with_agent(self) -> None:
    """Test agents command when an agent is loaded."""
    agent_def = AgentDefinition(
      name="test-agent",
      description="A test agent",
      model="llama3.2:latest",
      tools=["read", "write"],
    )

    agent = self._make_agent(agent_def=agent_def)
    command = create_agents_command()
    result = await command.handler("", agent, Mock())

    assert "Current agent:" in result
    assert "test-agent" in result
    assert "A test agent" in result
    assert "llama3.2:latest" in result
    assert "read, write" in result

  @pytest.mark.asyncio
  async def test_agents_command_without_model(self) -> None:
    """Test agents command when agent has no model specified."""
    agent_def = AgentDefinition(
      name="simple-agent",
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
      name="no-tools-agent",
      description="An agent without tools",
      tools=(),
      model="llama3.2:latest",
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
      name="test-agent",
      description="A test agent",
      tools=(),
    )

    agent = self._make_agent(agent_def=agent_def)
    command = create_agents_command()

    result1 = await command.handler("", agent, Mock())
    result2 = await command.handler("some args", agent, Mock())

    # Both should return the same output
    assert result1 == result2
