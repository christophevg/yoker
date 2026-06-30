"""Tests for multi-provider backend configuration (Phase 1 task 6.3)."""

import pytest

from yoker.config import (
  AnthropicConfig,
  AnthropicParameters,
  BackendConfig,
  OllamaConfig,
  OllamaParameters,
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

    # Known providers (ollama, openai, anthropic) require their config
    # Unknown providers don't require specific config

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
    """OpenAIParameters defaults to None to allow provider defaults."""
    params = OpenAIParameters()
    assert params.temperature is None
    assert params.top_p is None
    assert params.max_tokens is None
    assert params.max_completion_tokens is None
    assert params.presence_penalty is None
    assert params.frequency_penalty is None
    assert params.seed is None
    assert params.reasoning_effort is None

  def test_openai_parameters_validation(self) -> None:
    """OpenAIParameters validates temperature, top_p, and reasoning_effort."""
    # Temperature out of range
    with pytest.raises(ValidationError):
      OpenAIParameters(temperature=3.0)  # > 2.0

    # Top_p out of range
    with pytest.raises(ValidationError):
      OpenAIParameters(top_p=1.5)  # > 1.0

    # max_tokens must be positive
    with pytest.raises(ValidationError):
      OpenAIParameters(max_tokens=-1)

    # reasoning_effort must be valid
    with pytest.raises(ValidationError):
      OpenAIParameters(reasoning_effort="invalid")  # not in ("low", "medium", "high", "xhigh")


class TestAnthropicConfig:
  """Tests for Anthropic backend configuration (Phase 3 forward declaration)."""

  def test_anthropic_config_defaults(self) -> None:
    """AnthropicConfig has sensible defaults."""
    config = AnthropicConfig()
    assert config.api_key is None
    assert config.model == "claude-3-5-sonnet-20241022"
    assert config.base_url is None
    assert config.timeout_seconds == 60
    assert isinstance(config.parameters, AnthropicParameters)
    # max_tokens is in parameters now, with default 4096 (required by Anthropic API)
    assert config.parameters.max_tokens == 4096

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
    """AnthropicParameters has required max_tokens default and optional parameters."""
    params = AnthropicParameters()
    # max_tokens is REQUIRED by Anthropic API, so it must have a default
    assert params.max_tokens == 4096
    # All other parameters default to None
    assert params.temperature is None
    assert params.top_p is None
    assert params.top_k is None
    assert params.budget_tokens is None
    assert params.stop_sequences is None

  def test_anthropic_parameters_validation(self) -> None:
    """AnthropicParameters validates temperature, top_p, max_tokens, and budget_tokens."""
    # Temperature out of range (Anthropic uses 0.0-1.0)
    with pytest.raises(ValidationError):
      AnthropicParameters(temperature=1.5)  # > 1.0

    # Top_p out of range
    with pytest.raises(ValidationError):
      AnthropicParameters(top_p=1.5)  # > 1.0

    # Max_tokens must be positive
    with pytest.raises(ValidationError):
      AnthropicParameters(max_tokens=-1)

    # Budget_tokens must be positive if provided
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


class TestBackendConfigParams:
  """Tests for BackendConfig.params property (simplified LitellmBackend design)."""

  def test_params_flattens_ollama_config(self) -> None:
    """BackendConfig.params flattens OllamaConfig to dict."""

    backend = BackendConfig(
      provider="ollama",
      ollama=OllamaConfig(
        model="llama3.2:latest",
        base_url="http://localhost:11434",
        timeout_seconds=60,
        parameters=OllamaParameters(temperature=0.7, top_p=0.9, top_k=40, num_ctx=4096),
      ),
    )
    params = backend.params

    # Should include all OllamaConfig fields
    assert params["model"] == "llama3.2:latest"
    assert params["base_url"] == "http://localhost:11434"
    assert params["timeout_seconds"] == 60
    # Parameters should be included as nested dict (asdict behavior)
    assert "parameters" in params

  def test_params_flattens_openai_config(self) -> None:
    """BackendConfig.params flattens OpenAIConfig to dict."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(
        model="gpt-4o",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
      ),
      ollama=None,
    )
    params = backend.params

    # Should include all OpenAIConfig fields
    assert params["model"] == "gpt-4o"
    assert params["api_key"] == "sk-test"
    assert params["base_url"] == "https://api.openai.com/v1"

  def test_params_flattens_anthropic_config(self) -> None:
    """BackendConfig.params flattens AnthropicConfig to dict."""
    backend = BackendConfig(
      provider="anthropic",
      anthropic=AnthropicConfig(
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-test",
        parameters=AnthropicParameters(max_tokens=4096),
      ),
      ollama=None,
    )
    params = backend.params

    # Should include all AnthropicConfig fields
    assert params["model"] == "claude-3-5-sonnet-20241022"
    assert params["api_key"] == "sk-ant-test"
    # max_tokens is now in parameters (nested dict)
    assert "parameters" in params
    assert params["parameters"]["max_tokens"] == 4096

  def test_params_filters_none_values(self) -> None:
    """BackendConfig.params excludes None values from flattened dict."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(
        model="gpt-4o-mini",
        # api_key and base_url default to None
      ),
      ollama=None,
    )
    params = backend.params

    # None values should be filtered out
    assert "api_key" not in params
    assert "base_url" not in params
    # model should be present
    assert params["model"] == "gpt-4o-mini"

  def test_params_returns_empty_dict_for_none_config(self) -> None:
    """BackendConfig.params returns empty dict when sub-config is None."""
    backend = BackendConfig(
      provider="groq",  # Unknown provider
      ollama=None,
      openai=None,
      anthropic=None,
    )
    params = backend.params

    # Should return empty dict since no sub-config is set
    assert params == {}

  def test_params_includes_model_from_subconfig(self) -> None:
    """BackendConfig.params includes model field from sub-config."""
    backend = BackendConfig(
      provider="openai",
      openai=OpenAIConfig(model="gpt-4o"),
      ollama=None,
    )
    params = backend.params

    # model should be included
    assert params["model"] == "gpt-4o"
