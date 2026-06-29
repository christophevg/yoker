"""Tests for backend factory function."""

import pytest

from yoker.backends import create_backend
from yoker.backends.ollama import OllamaBackend
from yoker.config import Config
from yoker.exceptions import ConfigurationError


class TestCreateBackend:
  """Tests for create_backend factory function."""

  def test_create_backend_returns_ollama_backend_for_ollama_provider(self):
    """create_backend(Config()) returns OllamaBackend for default config."""
    config = Config()
    backend = create_backend(config)

    assert isinstance(backend, OllamaBackend)
    assert backend.provider == "ollama"

  def test_create_backend_returns_ollama_backend_with_ollama_config(self):
    """create_backend returns OllamaBackend when provider is explicitly set."""
    from yoker.config import BackendConfig, OllamaConfig

    config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          base_url="http://custom:11434",
          model="test-model",
        ),
      ),
    )
    backend = create_backend(config)

    assert isinstance(backend, OllamaBackend)
    assert backend.provider == "ollama"

  def test_create_backend_raises_configuration_error_for_unknown_provider(self):
    """create_backend raises ConfigurationError for unknown provider."""
    from yoker.config import BackendConfig

    # Create a config that bypasses validation (for testing)
    config = Config(backend=BackendConfig(provider="ollama"))
    # Manually set provider to unknown after creation (bypasses validator)
    object.__setattr__(config.backend, "provider", "unknown")

    with pytest.raises(ConfigurationError, match="Unknown provider"):
      create_backend(config)

  def test_create_backend_raises_not_implemented_for_openai(self):
    """create_backend raises NotImplementedError for openai provider."""
    from yoker.config import BackendConfig

    config = Config(backend=BackendConfig(provider="openai"))

    with pytest.raises(NotImplementedError, match="OpenAI backend not implemented"):
      create_backend(config)

  def test_create_backend_raises_not_implemented_for_anthropic(self):
    """create_backend raises NotImplementedError for anthropic provider."""
    from yoker.config import BackendConfig

    config = Config(backend=BackendConfig(provider="anthropic"))

    with pytest.raises(NotImplementedError, match="Anthropic backend not implemented"):
      create_backend(config)
