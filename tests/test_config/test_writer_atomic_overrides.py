"""Tests for atomic override application in config writer.

This test suite verifies that backend.provider and backend.<provider> are
applied atomically to avoid validation errors in BackendConfig.__post_init__.

Issue: When setting backend.provider to a known provider (gemini, openai, anthropic),
the BackendConfig validation requires the corresponding provider config to be set.
If we set provider first and config second, validation fails.

Solution: _apply_backend_provider_overrides ensures both are set in the same
dataclasses.replace() call.
"""

from yoker.config import Config
from yoker.config.providers import AnthropicConfig, GeminiConfig, OpenAIConfig
from yoker.config.writer import render_config_toml


class TestAtomicBackendProviderOverrides:
  """Test that backend provider overrides are applied atomically."""

  def test_gemini_provider_with_config_applied_atomically(self) -> None:
    """Gemini provider and config must be set together to avoid validation error."""
    config = Config()
    overrides = {
      "backend.provider": "gemini",
      "backend.gemini": GeminiConfig(),
      "backend.gemini.model": "gemini-2.5-flash-lite",
    }

    # This should not raise ValidationError
    toml = render_config_toml(config, overrides=overrides)

    # Verify the TOML contains the correct values
    assert 'provider = "gemini"' in toml
    assert 'model = "gemini-2.5-flash-lite"' in toml

  def test_openai_provider_with_config_applied_atomically(self) -> None:
    """OpenAI provider and config must be set together to avoid validation error."""
    config = Config()
    overrides = {
      "backend.provider": "openai",
      "backend.openai": OpenAIConfig(),
      "backend.openai.model": "gpt-4o-mini",
    }

    # This should not raise ValidationError
    toml = render_config_toml(config, overrides=overrides)

    # Verify the TOML contains the correct values
    assert 'provider = "openai"' in toml
    assert 'model = "gpt-4o-mini"' in toml

  def test_anthropic_provider_with_config_applied_atomically(self) -> None:
    """Anthropic provider and config must be set together to avoid validation error."""
    config = Config()
    overrides = {
      "backend.provider": "anthropic",
      "backend.anthropic": AnthropicConfig(),
      "backend.anthropic.model": "claude-haiku-4-5",
    }

    # This should not raise ValidationError
    toml = render_config_toml(config, overrides=overrides)

    # Verify the TOML contains the correct values
    assert 'provider = "anthropic"' in toml
    assert 'model = "claude-haiku-4-5"' in toml

  def test_ollama_provider_no_config_needed(self) -> None:
    """Ollama has default_factory, so no config initialization needed."""
    config = Config()
    overrides = {
      "backend.provider": "ollama",
      "backend.ollama.model": "llama3.2",
    }

    # This should work without explicit OllamaConfig()
    toml = render_config_toml(config, overrides=overrides)

    # Verify the TOML contains the correct values
    assert 'provider = "ollama"' in toml
    assert 'model = "llama3.2"' in toml

  def test_multiple_overrides_applied_correctly(self) -> None:
    """All backend overrides should be applied, not just provider and config."""
    config = Config()
    overrides = {
      "backend.provider": "gemini",
      "backend.gemini": GeminiConfig(),
      "backend.gemini.model": "gemini-2.5-flash",
      "backend.gemini.api_key": "test-key-123",
    }

    # This should not raise ValidationError
    toml = render_config_toml(config, overrides=overrides)

    # Verify all overrides are applied
    assert 'provider = "gemini"' in toml
    assert 'model = "gemini-2.5-flash"' in toml
    assert 'api_key = "test-key-123"' in toml

  def test_provider_switching_works(self) -> None:
    """Switching from default provider to another should work."""
    # Start with default Config (ollama)
    config = Config()
    assert config.backend.provider == "ollama"

    # Switch to gemini
    overrides = {
      "backend.provider": "gemini",
      "backend.gemini": GeminiConfig(),
      "backend.gemini.model": "gemini-2.5-flash-lite",
    }

    # This should not raise ValidationError
    toml = render_config_toml(config, overrides=overrides)
    assert 'provider = "gemini"' in toml
