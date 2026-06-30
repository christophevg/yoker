"""Unit tests for trust boundary validation."""

import os
from unittest.mock import patch

import pytest

from yoker.backends.trust import (
  TrustBoundaryError,
  is_custom_base_url,
  validate_base_url_trust,
)
from yoker.config import (
  AnthropicConfig,
  BackendConfig,
  GeminiConfig,
  OllamaConfig,
  OpenAIConfig,
)


class TestIsCustomBaseUrl:
  """Tests for is_custom_base_url function."""

  def test_ollama_default_url_localhost(self) -> None:
    """Test Ollama default URL (localhost) is not custom."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(base_url="http://localhost:11434"),
    )
    assert not is_custom_base_url(backend)

  def test_ollama_default_url_ollama_com(self) -> None:
    """Test Ollama default URL (ollama.com) is not custom."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(base_url="https://ollama.com"),
    )
    assert not is_custom_base_url(backend)

  def test_ollama_custom_url(self) -> None:
    """Test Ollama custom URL is detected."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(base_url="http://custom.server:11434"),
    )
    assert is_custom_base_url(backend)

  def test_openai_default_url(self) -> None:
    """Test OpenAI default URL (None) is not custom."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(api_key="test", base_url=None),
    )
    assert not is_custom_base_url(backend)

  def test_openai_custom_url(self) -> None:
    """Test OpenAI custom URL is detected."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(api_key="test", base_url="https://custom.openai.com/v1"),
    )
    assert is_custom_base_url(backend)

  def test_anthropic_default_url(self) -> None:
    """Test Anthropic default URL (None) is not custom."""
    backend = BackendConfig(
      provider="anthropic",
      anthropic=AnthropicConfig(api_key="test", base_url=None),
    )
    assert not is_custom_base_url(backend)

  def test_anthropic_custom_url(self) -> None:
    """Test Anthropic custom URL is detected."""
    backend = BackendConfig(
      provider="anthropic",
      anthropic=AnthropicConfig(api_key="test", base_url="https://custom.anthropic.com/v1"),
    )
    assert is_custom_base_url(backend)

  def test_gemini_default_url(self) -> None:
    """Test Gemini default URL (None) is not custom."""
    backend = BackendConfig(
      provider="gemini",
      gemini=GeminiConfig(api_key="test", base_url=None),
    )
    assert not is_custom_base_url(backend)

  def test_gemini_custom_url(self) -> None:
    """Test Gemini custom URL is detected."""
    backend = BackendConfig(
      provider="gemini",
      gemini=GeminiConfig(api_key="test", base_url="https://custom.gemini.com/v1"),
    )
    assert is_custom_base_url(backend)


class TestValidateBaseUrlTrust:
  """Tests for validate_base_url_trust function."""

  def test_default_url_passes(self) -> None:
    """Test default URL passes validation."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(base_url="http://localhost:11434"),
    )
    # Should not raise
    validate_base_url_trust(backend, interactive=False)

  def test_custom_url_batch_mode_raises(self) -> None:
    """Test custom URL in batch mode raises TrustBoundaryError."""
    import os

    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(base_url="http://custom.server:11434"),
    )
    # Unset environment variable to test batch mode behavior
    original_value = os.environ.get("YOKER_ALLOW_CUSTOM_BASE_URL")
    if "YOKER_ALLOW_CUSTOM_BASE_URL" in os.environ:
      del os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"]

    try:
      with pytest.raises(TrustBoundaryError):
        validate_base_url_trust(backend, interactive=False)
    finally:
      # Restore original value
      if original_value is not None:
        os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"] = original_value

  def test_custom_url_with_env_var_passes(self) -> None:
    """Test custom URL with YOKER_ALLOW_CUSTOM_BASE_URL=1 passes."""
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(base_url="http://custom.server:11434"),
    )
    with patch.dict(
      os.environ, {os.environ.get("ENV_ALLOW_CUSTOM_BASE_URL", "YOKER_ALLOW_CUSTOM_BASE_URL"): "1"}
    ):
      # Should not raise
      validate_base_url_trust(backend, interactive=False)

  def test_openai_custom_url_batch_mode_raises(self) -> None:
    """Test OpenAI custom URL in batch mode raises."""
    import os

    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(api_key="test", base_url="https://custom.openai.com/v1"),
    )
    # Unset environment variable to test batch mode behavior
    original_value = os.environ.get("YOKER_ALLOW_CUSTOM_BASE_URL")
    if "YOKER_ALLOW_CUSTOM_BASE_URL" in os.environ:
      del os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"]

    try:
      with pytest.raises(TrustBoundaryError):
        validate_base_url_trust(backend, interactive=False)
    finally:
      # Restore original value
      if original_value is not None:
        os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"] = original_value

  def test_anthropic_custom_url_batch_mode_raises(self) -> None:
    """Test Anthropic custom URL in batch mode raises."""
    import os

    backend = BackendConfig(
      provider="anthropic",
      anthropic=AnthropicConfig(api_key="test", base_url="https://custom.anthropic.com/v1"),
    )
    # Unset environment variable to test batch mode behavior
    original_value = os.environ.get("YOKER_ALLOW_CUSTOM_BASE_URL")
    if "YOKER_ALLOW_CUSTOM_BASE_URL" in os.environ:
      del os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"]

    try:
      with pytest.raises(TrustBoundaryError):
        validate_base_url_trust(backend, interactive=False)
    finally:
      # Restore original value
      if original_value is not None:
        os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"] = original_value


class TestDefaultBaseUrls:
  """Tests for DEFAULT_BASE_URLS class variable on provider configs."""

  def test_ollama_defaults(self) -> None:
    """Test Ollama has multiple default URLs."""
    assert OllamaConfig.DEFAULT_BASE_URLS == ["http://localhost:11434", "https://ollama.com"]

  def test_openai_default(self) -> None:
    """Test OpenAI default URL is None."""
    assert OpenAIConfig.DEFAULT_BASE_URLS is None

  def test_anthropic_default(self) -> None:
    """Test Anthropic default URL is None."""
    assert AnthropicConfig.DEFAULT_BASE_URLS is None

  def test_gemini_default(self) -> None:
    """Test Gemini default URL is None."""
    assert GeminiConfig.DEFAULT_BASE_URLS is None
