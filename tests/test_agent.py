"""Tests for yoker agent module."""

import pytest

from yoker.agent import Agent
from yoker.config import BackendConfig, Config, OllamaConfig


class TestAgent:
  """Tests for the Agent class."""

  def test_agent_initialization(self) -> None:
    """Test that Agent initializes with default config."""
    # Pass explicit config to prevent auto-discovery from picking up local config
    agent = Agent(config=Config())
    # Default model comes from Config
    assert agent.model == Config().backend.ollama.model
    assert agent.tool_registry is not None
    assert agent.tool_registry.get("read") is not None
    assert agent.config is not None

  def test_agent_custom_model(self) -> None:
    """Test that Agent accepts model via config."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="custom-model")))
    agent = Agent(config=config)
    assert agent.model == "custom-model"

  def test_agent_with_config(self) -> None:
    """Test that Agent accepts config."""
    config = Config(backend=BackendConfig(ollama=OllamaConfig(model="test-model")))
    agent = Agent(config=config)
    assert agent.model == "test-model"

  def test_tools_available(self) -> None:
    """Test that tools are available."""
    from yoker.tools import AVAILABLE_TOOLS

    assert AVAILABLE_TOOLS.get("read") is not None

  def test_recursion_depth_default(self) -> None:
    """Test that recursion depth starts at 0 by default."""
    agent = Agent(config=Config())
    assert agent._recursion_depth == 0
    assert agent._max_recursion_depth == agent.config.tools.agent.max_recursion_depth

  def test_recursion_depth_custom(self) -> None:
    """Test that recursion depth can be set via internal parameter."""
    agent = Agent(config=Config(), _recursion_depth=2)
    assert agent._recursion_depth == 2

  def test_agent_tool_available(self) -> None:
    """Test that agent tool is available in tool registry."""
    agent = Agent(config=Config())
    assert agent.tool_registry.get("agent") is not None

  def test_inject_skill_context_adds_system_message(self) -> None:
    """Test that inject_skill_context appends a system message."""
    agent = Agent(config=Config())
    agent._core.skill_registry = None
    from yoker.skills import Skill, SkillRegistry

    skill_registry = SkillRegistry()
    skill_registry.register(
      Skill(name="commit", description="Guide commits", content="Commit instructions")
    )
    agent._core.skill_registry = skill_registry

    initial_count = len(agent.context.get_messages())
    agent.inject_skill_context("commit", "fix bug")

    messages = agent.context.get_messages()
    assert len(messages) == initial_count + 1
    last_message = messages[-1]
    assert last_message["role"] == "system"
    assert "commit" in last_message["content"]
    assert "fix bug" in last_message["content"]
    assert "Commit instructions" in last_message["content"]

  def test_inject_skill_context_unknown_skill_raises(self) -> None:
    """Test that inject_skill_context raises SkillError for unknown skills."""
    from yoker.exceptions import SkillError

    agent = Agent(config=Config())

    with pytest.raises(SkillError):
      agent.inject_skill_context("unknown")
