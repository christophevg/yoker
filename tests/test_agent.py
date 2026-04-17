"""Tests for yoker agent module."""

from yoker.agent import Agent


class TestAgent:
  """Tests for the Agent class."""

  def test_agent_initialization(self) -> None:
    """Test that Agent initializes with default model."""
    agent = Agent()
    assert agent.model == "glm-5:cloud"
    assert agent.tools is not None
    assert "read" in agent.tools

  def test_agent_custom_model(self) -> None:
    """Test that Agent accepts custom model."""
    agent = Agent(model="llama3.2:latest")
    assert agent.model == "llama3.2:latest"

  def test_tools_available(self) -> None:
    """Test that tools are available."""
    from yoker.tools import AVAILABLE_TOOLS

    assert "read" in AVAILABLE_TOOLS
    assert callable(AVAILABLE_TOOLS["read"])