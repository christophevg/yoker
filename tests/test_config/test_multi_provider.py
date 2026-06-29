"""Tests for multi-provider backend configuration (Phase 1 task 6.3)."""

import pytest

from yoker.config import (
  AnthropicConfig,
  AnthropicParameters,
  BackendConfig,
  OllamaConfig,
  OpenAIConfig,
  OpenAIParameters,
)
from yoker.exceptions import ValidationError


class TestBackendConfigTaggedUnion:
  """Tests for BackendConfig discriminated union (tagged union shape)."""

  def test_backend_config_defaults_to_ollama(self) -> None:
    """BackendConfig() defaults to provider='ollama' with ollama config."""
    backend = BackendConfig()
    assert backend.provider == "ollama"
    assert isinstance(backend.ollama, OllamaConfig)
    assert backend.openai is None
    assert backend.anthropic is None

  def test_backend_config_accepts_ollama_explicit(self) -> None:
    """BackendConfig can be explicitly configured for Ollama."""
    backend = BackendConfig(provider="ollama", ollama=OllamaConfig(model="llama3.1:latest"))
    assert backend.provider == "ollama"
    assert backend.ollama.model == "llama3.1:latest"
    assert backend.openai is None
    assert backend.anthropic is None

  def test_backend_config_accepts_openai(self) -> None:
    """BackendConfig can be configured for OpenAI (Phase 2)."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(api_key="sk-test", model="gpt-4o"),
      ollama=None,
    )
    assert backend.provider == "openai"
    assert backend.openai is not None
    assert backend.openai.api_key == "sk-test"
    assert backend.openai.model == "gpt-4o"
    assert backend.ollama is None
    assert backend.anthropic is None

  def test_backend_config_accepts_anthropic(self) -> None:
    """BackendConfig can be configured for Anthropic (Phase 3)."""
    backend = BackendConfig(
      provider="anthropic",
      anthropic=AnthropicConfig(api_key="sk-ant-test", model="claude-3-5-sonnet-20241022"),
      ollama=None,
    )
    assert backend.provider == "anthropic"
    assert backend.anthropic is not None
    assert backend.anthropic.api_key == "sk-ant-test"
    assert backend.anthropic.model == "claude-3-5-sonnet-20241022"
    assert backend.ollama is None
    assert backend.openai is None

  def test_backend_config_provider_validation(self) -> None:
    """BackendConfig allows any provider (litellm supports 100+ providers)."""
    # Unknown providers are allowed and use litellm
    backend = BackendConfig(
      provider="groq",  # Unknown provider, but allowed
      ollama=None,
      openai=None,
      anthropic=None,
    )
    assert backend.provider == "groq"

    # Known providers must be in whitelist
    # This validation still runs for known providers
    from yoker.config import _ALLOWED_PROVIDERS

    assert "ollama" in _ALLOWED_PROVIDERS
    assert "openai" in _ALLOWED_PROVIDERS
    assert "anthropic" in _ALLOWED_PROVIDERS

  def test_backend_config_ollama_required_when_provider_ollama(self) -> None:
    """BackendConfig requires ollama config when provider='ollama'."""
    with pytest.raises(ValidationError) as exc_info:
      BackendConfig(provider="ollama", ollama=None)
    assert "backend.ollama" in str(exc_info.value)

  def test_backend_config_openai_none_allowed_when_provider_ollama(self) -> None:
    """BackendConfig accepts openai=None when provider='ollama'."""
    # Phase 1 allows openai/anthropic to be None when provider is not openai/anthropic
    backend = BackendConfig(provider="ollama", ollama=OllamaConfig(), openai=None, anthropic=None)
    assert backend.provider == "ollama"
    assert backend.openai is None
    assert backend.anthropic is None


class TestOpenAIConfig:
  """Tests for OpenAI backend configuration (Phase 2 forward declaration)."""

  def test_openai_config_defaults(self) -> None:
    """OpenAIConfig has sensible defaults."""
    config = OpenAIConfig()
    assert config.api_key is None
    assert config.model == "gpt-4o-mini"
    assert config.base_url is None
    assert config.timeout_seconds == 60
    assert isinstance(config.parameters, OpenAIParameters)

  def test_openai_config_with_api_key(self) -> None:
    """OpenAIConfig accepts API key."""
    config = OpenAIConfig(api_key="sk-test-key")
    assert config.api_key == "sk-test-key"

  def test_openai_config_base_url_validation(self) -> None:
    """OpenAIConfig validates base_url if provided."""
    # Valid URL should work
    config = OpenAIConfig(base_url="https://api.openai.com/v1")
    assert config.base_url == "https://api.openai.com/v1"

    # Invalid URL should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
      OpenAIConfig(base_url="not-a-valid-url")
    assert "backend.openai.base_url" in str(exc_info.value)

  def test_openai_parameters_defaults(self) -> None:
    """OpenAIParameters has sensible defaults."""
    params = OpenAIParameters()
    assert params.temperature == 0.7
    assert params.top_p == 0.9
    assert params.max_tokens is None

  def test_openai_parameters_validation(self) -> None:
    """OpenAIParameters validates temperature and top_p."""
    # Temperature out of range
    with pytest.raises(ValidationError):
      OpenAIParameters(temperature=3.0)  # > 2.0

    # Top_p out of range
    with pytest.raises(ValidationError):
      OpenAIParameters(top_p=1.5)  # > 1.0

    # max_tokens must be positive
    with pytest.raises(ValidationError):
      OpenAIParameters(max_tokens=-1)


class TestAnthropicConfig:
  """Tests for Anthropic backend configuration (Phase 3 forward declaration)."""

  def test_anthropic_config_defaults(self) -> None:
    """AnthropicConfig has sensible defaults."""
    config = AnthropicConfig()
    assert config.api_key is None
    assert config.model == "claude-3-5-sonnet-20241022"
    assert config.base_url is None
    assert config.timeout_seconds == 60
    assert config.max_tokens == 4096  # Q13: required by Anthropic API, sensible default
    assert isinstance(config.parameters, AnthropicParameters)
    assert config.parameters.budget_tokens == 1024  # Q12: dedicated field with sensible default

  def test_anthropic_config_with_api_key(self) -> None:
    """AnthropicConfig accepts API key."""
    config = AnthropicConfig(api_key="sk-ant-test")
    assert config.api_key == "sk-ant-test"

  def test_anthropic_config_base_url_validation(self) -> None:
    """AnthropicConfig validates base_url if provided."""
    # Valid URL should work
    config = AnthropicConfig(base_url="https://api.anthropic.com")
    assert config.base_url == "https://api.anthropic.com"

    # Invalid URL should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
      AnthropicConfig(base_url="not-a-valid-url")
    assert "backend.anthropic.base_url" in str(exc_info.value)

  def test_anthropic_parameters_defaults(self) -> None:
    """AnthropicParameters has sensible defaults."""
    params = AnthropicParameters()
    assert params.temperature == 0.7
    assert params.top_p == 0.9
    assert params.top_k is None
    assert params.budget_tokens == 1024

  def test_anthropic_parameters_validation(self) -> None:
    """AnthropicParameters validates temperature, top_p, and budget_tokens."""
    # Temperature out of range (Anthropic uses 0.0-1.0)
    with pytest.raises(ValidationError):
      AnthropicParameters(temperature=1.5)  # > 1.0

    # Top_p out of range
    with pytest.raises(ValidationError):
      AnthropicParameters(top_p=1.5)  # > 1.0

    # Budget_tokens must be positive
    with pytest.raises(ValidationError):
      AnthropicParameters(budget_tokens=-1)


class TestApiKeyCliExclusion:
  """Tests for api_key CLI exclusion (Q6 amendment, H1 resolved)."""

  def test_ollama_api_key_has_cli_false_metadata(self) -> None:
    """OllamaConfig.api_key has metadata={'cli': False}."""
    import dataclasses

    fields = dataclasses.fields(OllamaConfig)
    api_key_field = next(f for f in fields if f.name == "api_key")
    assert api_key_field.metadata.get("cli") is False

  def test_openai_api_key_has_cli_false_metadata(self) -> None:
    """OpenAIConfig.api_key has metadata={'cli': False}."""
    import dataclasses

    fields = dataclasses.fields(OpenAIConfig)
    api_key_field = next(f for f in fields if f.name == "api_key")
    assert api_key_field.metadata.get("cli") is False

  def test_anthropic_api_key_has_cli_false_metadata(self) -> None:
    """AnthropicConfig.api_key has metadata={'cli': False}."""
    import dataclasses

    fields = dataclasses.fields(AnthropicConfig)
    api_key_field = next(f for f in fields if f.name == "api_key")
    assert api_key_field.metadata.get("cli") is False


class TestOldTomlLoading:
  """Tests for backward compatibility with old TOML files."""

  def test_old_toml_single_ollama_shape_loads(self) -> None:
    """Old TOML files with single-Ollama shape load unchanged."""
    # This test verifies that a TOML file written by the wizard
    # before the multi-provider change still loads correctly.
    # The exact shape will be verified in integration tests;
    # here we verify the config accepts None for openai/anthropic.
    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(
        base_url="http://localhost:11434",
        model="llama3.2:latest",
        timeout_seconds=60,
      ),
      openai=None,
      anthropic=None,
    )
    assert backend.provider == "ollama"
    assert backend.ollama.model == "llama3.2:latest"
    assert backend.openai is None
    assert backend.anthropic is None
