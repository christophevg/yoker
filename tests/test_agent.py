"""Tests for yoker agent module."""

from yoker.agent import Agent
from yoker.config import BackendConfig, Config, OllamaConfig


class TestAgent:
  """Tests for the Agent class."""

  def test_agent_initialization(self) -> None:
    """Test that Agent initializes with default config."""
    agent = Agent()
    # Default model comes from Config
    assert agent.model == Config().backend.ollama.model
    assert agent.tools is not None
    assert "read" in agent.tools
    assert agent.config is not None

  def test_agent_custom_model(self) -> None:
    """Test that Agent accepts custom model."""
    agent = Agent(model="custom-model")
    assert agent.model == "custom-model"

  def test_agent_with_config(self) -> None:
    """Test that Agent accepts config."""
    config = Config(
      backend=BackendConfig(
        ollama=OllamaConfig(model="test-model")
      )
    )
    agent = Agent(config=config)
    assert agent.model == "test-model"

  def test_tools_available(self) -> None:
    """Test that tools are available."""
    from yoker.tools import AVAILABLE_TOOLS

    assert "read" in AVAILABLE_TOOLS
    assert callable(AVAILABLE_TOOLS["read"])
