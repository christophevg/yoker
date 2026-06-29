"""Tests for backend factory function."""

import os
from unittest.mock import patch

from yoker.backends import create_backend
from yoker.backends.litellm import LitellmBackend
from yoker.backends.ollama import OllamaBackend
from yoker.config import Config


class TestCreateBackend:
  """Tests for create_backend factory function."""

  def test_create_backend_returns_ollama_backend_for_ollama_provider(self):
    """create_backend(Config()) returns OllamaBackend for default config."""
    config = Config()
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
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
    with patch.dict(os.environ, {"YOKER_ALLOW_CUSTOM_BASE_URL": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, OllamaBackend)
    assert backend.provider == "ollama"

  def test_create_backend_returns_litellm_for_unknown_provider(self):
    """create_backend returns LitellmBackend for unknown providers."""
    from yoker.config import BackendConfig

    # Create a config with an unknown provider
    # Note: Unknown providers use LitellmBackend
    config = Config(
      backend=BackendConfig(
        provider="groq",  # Not explicitly handled, but litellm supports it
        ollama=None,
        openai=None,
        anthropic=None,
      )
    )
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, LitellmBackend)
    assert backend.provider == "groq"

  def test_create_backend_returns_litellm_for_openai(self):
    """create_backend returns LitellmBackend for openai provider."""
    from yoker.config import BackendConfig, OpenAIConfig

    config = Config(
      backend=BackendConfig(
        provider="openai",
        openai=OpenAIConfig(api_key="test-key"),
      )
    )
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, LitellmBackend)
    assert backend.provider == "openai"

  def test_create_backend_returns_litellm_for_anthropic(self):
    """create_backend returns LitellmBackend for anthropic provider."""
    from yoker.config import AnthropicConfig, BackendConfig

    config = Config(
      backend=BackendConfig(
        provider="anthropic",
        anthropic=AnthropicConfig(api_key="test-key"),
      )
    )
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, LitellmBackend)
    assert backend.provider == "anthropic"
