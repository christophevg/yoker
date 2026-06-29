"""Tests for the with_model helper function.

Task 6.7: Subagent spawn provider-agnostic.
"""

from yoker.backends import with_model
from yoker.config import (
  AnthropicConfig,
  BackendConfig,
  Config,
  OllamaConfig,
  OpenAIConfig,
)


class TestWithModel:
  """Tests for the with_model helper function."""

  def test_with_model_ollama(self) -> None:
    """Test with_model creates a copy with model overridden for Ollama."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(
        model="llama3.1:8b",
        base_url="http://localhost:11434",
        timeout_seconds=60,
      ),
    )

    new_backend = with_model(backend, "llama3.2:latest")

    # Should preserve provider
    assert new_backend.provider == "ollama"

    # Should preserve other Ollama settings
    assert new_backend.ollama is not None
    assert new_backend.ollama.base_url == "http://localhost:11434"
    assert new_backend.ollama.timeout_seconds == 60

    # Should override model
    assert new_backend.ollama.model == "llama3.2:latest"

    # Should be a different object
    assert new_backend is not backend
    assert new_backend.ollama is not backend.ollama

  def test_with_model_openai(self) -> None:
    """Test with_model creates a copy with model overridden for OpenAI."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(
        model="gpt-4",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
      ),
    )

    new_backend = with_model(backend, "gpt-4o")

    # Should preserve provider
    assert new_backend.provider == "openai"

    # Should preserve other OpenAI settings
    assert new_backend.openai is not None
    assert new_backend.openai.api_key == "sk-test"
    assert new_backend.openai.base_url == "https://api.openai.com/v1"

    # Should override model
    assert new_backend.openai.model == "gpt-4o"

    # Should be a different object
    assert new_backend is not backend
    assert new_backend.openai is not backend.openai

  def test_with_model_anthropic(self) -> None:
    """Test with_model creates a copy with model overridden for Anthropic."""
    backend = BackendConfig(
      provider="anthropic",
      anthropic=AnthropicConfig(
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-test",
      ),
    )

    new_backend = with_model(backend, "claude-3-5-haiku-20241022")

    # Should preserve provider
    assert new_backend.provider == "anthropic"

    # Should preserve other Anthropic settings
    assert new_backend.anthropic is not None
    assert new_backend.anthropic.api_key == "sk-ant-test"

    # Should override model
    assert new_backend.anthropic.model == "claude-3-5-haiku-20241022"

    # Should be a different object
    assert new_backend is not backend
    assert new_backend.anthropic is not backend.anthropic

  def test_with_model_preserves_none_fields(self) -> None:
    """Test that with_model preserves None for other provider configs."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(model="llama3.1:8b"),
      openai=None,
      anthropic=None,
    )

    new_backend = with_model(backend, "llama3.2:latest")

    # Should preserve None fields
    assert new_backend.openai is None
    assert new_backend.anthropic is None

  def test_with_model_ollama_is_primary_path(self) -> None:
    """Test that with_model correctly handles Ollama as the primary path."""
    # In Phase 1, Ollama is the primary provider
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(model="llama3.1:8b"),
    )

    new_backend = with_model(backend, "llama3.2:latest")

    # Should preserve provider
    assert new_backend.provider == "ollama"
    assert new_backend.ollama is not None
    assert new_backend.ollama.model == "llama3.2:latest"


class TestWithModelIntegration:
  """Integration tests for with_model with subagent spawn."""

  def test_subagent_inherits_parent_provider_ollama(self) -> None:
    """Test that subagent inherits parent's Ollama provider."""
    from yoker.agent import Agent
    from yoker.agents import AgentDefinition
    from yoker.builtin.agent import _create_subagent

    parent_config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          model="parent-model",
          base_url="http://custom:11434",
          timeout_seconds=120,
        ),
      ),
    )

    # Mock parent agent
    from unittest.mock import MagicMock

    parent = MagicMock(spec=Agent)
    parent.config = parent_config
    parent.recursion_depth = 0
    parent.context = MagicMock()
    parent.context.get_session_id.return_value = "parent-session"

    # Create subagent with model override
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=(),
      model="child-model",
    )

    subagent = _create_subagent(parent, agent_def)

    # Should inherit provider
    assert subagent.config.backend.provider == "ollama"

    # Should inherit other Ollama settings
    assert subagent.config.backend.ollama is not None
    assert subagent.config.backend.ollama.base_url == "http://custom:11434"
    assert subagent.config.backend.ollama.timeout_seconds == 120

    # Should override model
    assert subagent.config.backend.ollama.model == "child-model"

  # Note: OpenAI and Anthropic provider tests will be added in Phase 2/3
  # when those backends are implemented. Phase 1 only supports Ollama.

  def test_subagent_no_model_uses_parent_config(self) -> None:
    """Test that subagent with no model uses parent config unchanged."""
    from unittest.mock import MagicMock

    from yoker.agent import Agent
    from yoker.agents import AgentDefinition
    from yoker.builtin.agent import _create_subagent

    parent_config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(model="parent-model"),
      ),
    )

    parent = MagicMock(spec=Agent)
    parent.config = parent_config
    parent.recursion_depth = 0
    parent.context = MagicMock()
    parent.context.get_session_id.return_value = "parent-session"

    # No model in agent definition
    agent_def = AgentDefinition(
      simple_name="test",
      description="Test agent",
      tools=(),
      model=None,
    )

    subagent = _create_subagent(parent, agent_def)

    # Should use parent config unchanged
    assert subagent.config is parent_config
    assert subagent.config.backend.ollama is not None
    assert subagent.config.backend.ollama.model == "parent-model"
