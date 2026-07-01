"""Tests for :mod:`yoker.bootstrap.providers`.

Unit tests for provider metadata and registry.
"""

import pytest

from yoker.bootstrap.providers import (
  PROVIDER_ORDER,
  PROVIDERS,
  CuratedModel,
  get_curated_models,
  get_default_model,
  get_default_provider,
  get_provider_info,
)


class TestProviderRegistry:
  """Tests for the provider registry."""

  def test_providers_dict_has_all_known_providers(self) -> None:
    """PROVIDERS contains all expected providers."""
    assert "ollama" in PROVIDERS
    assert "openai" in PROVIDERS
    assert "anthropic" in PROVIDERS
    assert "gemini" in PROVIDERS

  def test_provider_order_matches_providers_dict(self) -> None:
    """PROVIDER_ORDER contains valid provider IDs."""
    for provider_id in PROVIDER_ORDER:
      assert provider_id in PROVIDERS

  def test_provider_order_starts_with_ollama(self) -> None:
    """Ollama is first in the order (backward compatibility)."""
    assert PROVIDER_ORDER[0] == "ollama"

  def test_all_providers_have_required_fields(self) -> None:
    """Each provider has all required fields."""
    for provider_id, provider in PROVIDERS.items():
      assert provider.id == provider_id
      assert provider.display_name
      assert provider.description
      assert isinstance(provider.requires_api_key, bool)
      assert isinstance(provider.has_local_app, bool)
      assert provider.account_url
      assert provider.docs_guide_url
      assert len(provider.curated_models) > 0
      assert provider.default_model


class TestProviderInfo:
  """Tests for ProviderInfo dataclass."""

  def test_ollama_has_local_app_and_no_required_key(self) -> None:
    """Ollama can use local app without API key."""
    ollama = PROVIDERS["ollama"]
    assert ollama.has_local_app is True
    assert ollama.requires_api_key is False

  def test_openai_requires_api_key(self) -> None:
    """OpenAI requires an API key."""
    openai = PROVIDERS["openai"]
    assert openai.has_local_app is False
    assert openai.requires_api_key is True
    assert openai.api_key_url is not None

  def test_anthropic_requires_api_key(self) -> None:
    """Anthropic requires an API key."""
    anthropic = PROVIDERS["anthropic"]
    assert anthropic.has_local_app is False
    assert anthropic.requires_api_key is True
    assert anthropic.api_key_url is not None

  def test_gemini_requires_api_key(self) -> None:
    """Gemini requires an API key."""
    gemini = PROVIDERS["gemini"]
    assert gemini.has_local_app is False
    assert gemini.requires_api_key is True
    assert gemini.api_key_url is not None


class TestGetProviderInfo:
  """Tests for get_provider_info function."""

  def test_get_ollama_provider_info(self) -> None:
    """Get Ollama provider info by id."""
    provider = get_provider_info("ollama")
    assert provider.id == "ollama"
    assert provider.display_name == "Ollama"

  def test_get_openai_provider_info(self) -> None:
    """Get OpenAI provider info by id."""
    provider = get_provider_info("openai")
    assert provider.id == "openai"
    assert provider.display_name == "OpenAI"

  def test_get_unknown_provider_raises_key_error(self) -> None:
    """Getting unknown provider raises KeyError."""
    with pytest.raises(KeyError):
      get_provider_info("unknown_provider")


class TestGetDefaultProvider:
  """Tests for get_default_provider function."""

  def test_default_provider_is_ollama(self) -> None:
    """Default provider is Ollama for backward compatibility."""
    provider = get_default_provider()
    assert provider.id == "ollama"


class TestGetCuratedModels:
  """Tests for get_curated_models function."""

  def test_ollama_has_models(self) -> None:
    """Ollama has curated models."""
    models = get_curated_models("ollama")
    assert len(models) > 0

  def test_openai_has_models(self) -> None:
    """OpenAI has curated models."""
    models = get_curated_models("openai")
    assert len(models) > 0

  def test_models_are_curated_model_type(self) -> None:
    """Returned models are CuratedModel instances."""
    models = get_curated_models("openai")
    for model in models:
      assert isinstance(model, CuratedModel)
      assert model.model_id
      assert model.label
      assert model.note


class TestGetDefaultModel:
  """Tests for get_default_model function."""

  def test_ollama_default_model(self) -> None:
    """Ollama default model matches provider config."""
    default = get_default_model("ollama")
    assert default == PROVIDERS["ollama"].default_model

  def test_openai_default_model(self) -> None:
    """OpenAI default model is gpt-4o-mini."""
    default = get_default_model("openai")
    assert default == "gpt-4o-mini"

  def test_anthropic_default_model(self) -> None:
    """Anthropic default model is claude-haiku-4-5."""
    default = get_default_model("anthropic")
    assert default == "claude-haiku-4-5"

  def test_gemini_default_model(self) -> None:
    """Gemini default model is gemini-2.5-flash-lite."""
    default = get_default_model("gemini")
    assert default == "gemini-2.5-flash-lite"


class TestCuratedModelsDataclass:
  """Tests for CuratedModel dataclass."""

  def test_curated_model_creation(self) -> None:
    """CuratedModel can be created with all fields."""
    model = CuratedModel(model_id="test-model", label="Test Model", note="A test model")
    assert model.model_id == "test-model"
    assert model.label == "Test Model"
    assert model.note == "A test model"

  def test_curated_model_is_frozen(self) -> None:
    """CuratedModel is immutable (frozen)."""
    model = CuratedModel(model_id="test-model", label="Test Model", note="A test model")
    with pytest.raises(AttributeError):
      model.model_id = "new-id"  # type: ignore


class TestProviderInfoDataclass:
  """Tests for ProviderInfo dataclass."""

  def test_provider_info_is_frozen(self) -> None:
    """ProviderInfo is immutable (frozen)."""
    provider = PROVIDERS["ollama"]
    with pytest.raises(AttributeError):
      provider.display_name = "New Name"  # type: ignore
