"""Tests for backend factory function."""

import os
from unittest.mock import patch

from yoker.backends import create_backend
from yoker.backends.litellm import LitellmBackend
from yoker.backends.ollama import OllamaBackend
from yoker.config import BackendConfig, Config, GenericConfig, OllamaConfig, OpenAIConfig


class TestCreateBackend:
  """Tests for create_backend factory function."""

  def test_create_backend_returns_ollama_backend_for_ollama_provider(self):
    """create_backend(Config()) returns OllamaBackend for default config."""
    config = Config()
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, OllamaBackend)

  def test_create_backend_returns_ollama_backend_with_ollama_config(self):
    """create_backend returns OllamaBackend when provider is explicitly set."""

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

  def test_create_backend_returns_litellm_for_unknown_provider(self):
    """create_backend returns LitellmBackend for unknown providers."""

    # Create a config with an unknown provider
    # Note: Unknown providers use LitellmBackend with GenericConfig
    config = Config(
      backend=BackendConfig(
        provider="groq",  # Not explicitly handled, but litellm supports it
        ollama=None,
        openai=None,
        anthropic=None,
      )
    )
    # GenericConfig is created automatically for unknown providers
    # Model can come from agent definition
    assert config.backend.provider == "groq"
    assert isinstance(config.backend.config, GenericConfig)

    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, LitellmBackend)

  def test_create_backend_returns_litellm_for_openai(self):
    """create_backend returns LitellmBackend for openai provider."""

    config = Config(
      backend=BackendConfig(
        provider="openai",
        openai=OpenAIConfig(api_key="test-key"),
      )
    )
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, LitellmBackend)

  def test_create_backend_returns_litellm_for_anthropic(self):
    """create_backend returns LitellmBackend for anthropic provider."""
    from yoker.config import AnthropicConfig

    config = Config(
      backend=BackendConfig(
        provider="anthropic",
        anthropic=AnthropicConfig(api_key="test-key"),
      )
    )
    with patch.dict(os.environ, {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(config)

    assert isinstance(backend, LitellmBackend)
