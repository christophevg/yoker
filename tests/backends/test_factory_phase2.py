"""Unit tests for backend factory."""

from unittest.mock import patch

import pytest

from yoker.backends.factory import create_backend
from yoker.backends.litellm import LitellmBackend
from yoker.backends.ollama import OllamaBackend
from yoker.config import (
  AnthropicConfig,
  BackendConfig,
  Config,
  OllamaConfig,
  OpenAIConfig,
)


class TestCreateBackend:
  """Tests for create_backend factory function."""

  @pytest.fixture
  def mock_config_ollama(self) -> Config:
    """Create a mock Config with Ollama backend."""
    return Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(model="llama3.2"),
      )
    )

  @pytest.fixture
  def mock_config_openai(self) -> Config:
    """Create a mock Config with OpenAI backend."""
    return Config(
      backend=BackendConfig(
        provider="openai",
        openai=OpenAIConfig(api_key="test-key"),
      )
    )

  @pytest.fixture
  def mock_config_anthropic(self) -> Config:
    """Create a mock Config with Anthropic backend."""
    return Config(
      backend=BackendConfig(
        provider="anthropic",
        anthropic=AnthropicConfig(api_key="test-key"),
      )
    )

  def test_create_backend_ollama(self, mock_config_ollama: Config) -> None:
    """Test create_backend returns OllamaBackend for provider='ollama'."""
    with patch.dict("os.environ", {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(mock_config_ollama)
      assert isinstance(backend, OllamaBackend)
      assert backend.provider == "ollama"

  def test_create_backend_openai(self, mock_config_openai: Config) -> None:
    """Test create_backend returns LitellmBackend for provider='openai'."""
    with patch.dict("os.environ", {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(mock_config_openai)
      assert isinstance(backend, LitellmBackend)
      assert backend.provider == "openai"

  def test_create_backend_anthropic(self, mock_config_anthropic: Config) -> None:
    """Test create_backend returns LitellmBackend for provider='anthropic'."""
    with patch.dict("os.environ", {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(mock_config_anthropic)
      assert isinstance(backend, LitellmBackend)
      assert backend.provider == "anthropic"

  def test_create_backend_unknown_provider(self) -> None:
    """Test create_backend returns LitellmBackend for unknown provider."""
    # Create a mock config with an unknown provider
    # This tests the "litellm supports 100+ providers" feature
    # Note: Unknown providers don't need provider-specific config
    mock_config = Config(
      backend=BackendConfig(
        provider="groq",  # Not explicitly handled, but litellm supports it
        ollama=None,  # Not required for unknown providers
        openai=None,
        anthropic=None,
      )
    )
    with patch.dict("os.environ", {"YOKER_DEV_MODE": "1"}):
      backend = create_backend(mock_config)
      assert isinstance(backend, LitellmBackend)
      assert backend.provider == "groq"

  def test_create_backend_custom_url_trust_boundary(self) -> None:
    """Test create_backend validates custom base_url trust boundary."""
    import os

    mock_config = Config(
      backend=BackendConfig(
        provider="ollama",
        ollama=OllamaConfig(
          base_url="http://custom.server:11434",
          model="llama3.2",
        ),
      )
    )

    # Batch mode should raise TrustBoundaryError
    # Unset environment variable to test batch mode behavior
    original_value = os.environ.get("YOKER_ALLOW_CUSTOM_BASE_URL")
    if "YOKER_ALLOW_CUSTOM_BASE_URL" in os.environ:
      del os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"]

    try:
      from yoker.backends.trust import TrustBoundaryError

      with pytest.raises(TrustBoundaryError):
        create_backend(mock_config, interactive=False)

      # With environment variable override, should pass
      with patch.dict(os.environ, {"YOKER_ALLOW_CUSTOM_BASE_URL": "1"}):
        backend = create_backend(mock_config, interactive=False)
        assert isinstance(backend, OllamaBackend)
    finally:
      # Restore original value
      if original_value is not None:
        os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"] = original_value
