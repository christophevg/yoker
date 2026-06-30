"""Tests for :func:`yoker.bootstrap.wizard.build_bootstrap_overrides`.

This is the pure-logic helper that turns the wizard's collected choices
into the dotted-key override dict passed to :func:`write_config`. It is
unit-tested here because it is logic (not wizard IO); the wizard flow
itself is not unit-tested per the owner's PR #34 directive.

Extended for multi-provider support.
"""

from yoker.bootstrap.steps import ConnectionChoice
from yoker.bootstrap.wizard import (
  OLLAMA_CLOUD_BASE_URL,
  build_bootstrap_overrides,
)


class TestBuildBootstrapOverridesOllama:
  """``build_bootstrap_overrides`` for Ollama provider."""

  def test_app_path_only_sets_model(self) -> None:
    """The ollama-app path (no key) only overrides provider and model."""
    overrides = build_bootstrap_overrides("ollama", "llama3.2", ConnectionChoice(use_api_key=False))
    assert overrides["backend.provider"] == "ollama"
    assert overrides["backend.ollama.model"] == "llama3.2"

  def test_app_path_does_not_set_base_url(self) -> None:
    """The app path keeps the default localhost base_url (no override)."""
    overrides = build_bootstrap_overrides("ollama", "llama3.2", ConnectionChoice(use_api_key=False))
    assert "backend.ollama.base_url" not in overrides
    assert "backend.ollama.api_key" not in overrides

  def test_api_key_path_sets_api_key_and_cloud_base_url(self) -> None:
    """The API-key path sets the key AND points base_url at the cloud."""
    overrides = build_bootstrap_overrides(
      "ollama",
      "llama3.2",
      ConnectionChoice(use_api_key=True, api_key="ollama-abc123"),
    )
    assert overrides["backend.provider"] == "ollama"
    assert overrides["backend.ollama.model"] == "llama3.2"
    assert overrides["backend.ollama.api_key"] == "ollama-abc123"
    assert overrides["backend.ollama.base_url"] == OLLAMA_CLOUD_BASE_URL

  def test_api_key_path_uses_cloud_endpoint_not_localhost(self) -> None:
    """The cloud base_url is not the localhost default."""
    overrides = build_bootstrap_overrides(
      "ollama",
      "llama3.2",
      ConnectionChoice(use_api_key=True, api_key="ollama-abc123"),
    )
    assert overrides["backend.ollama.base_url"] != "http://localhost:11434"
    assert overrides["backend.ollama.base_url"].startswith("https://")

  def test_api_key_path_with_empty_key_falls_back_to_app_path(self) -> None:
    """An empty key is treated like the app path (no key, no cloud url)."""
    overrides = build_bootstrap_overrides(
      "ollama",
      "llama3.2",
      ConnectionChoice(use_api_key=True, api_key=None),
    )
    assert overrides["backend.provider"] == "ollama"
    assert overrides["backend.ollama.model"] == "llama3.2"
    assert "backend.ollama.api_key" not in overrides
    assert "backend.ollama.base_url" not in overrides


class TestBuildBootstrapOverridesOpenAI:
  """``build_bootstrap_overrides`` for OpenAI provider."""

  def test_with_api_key(self) -> None:
    """OpenAI with API key sets provider, model, and key."""
    overrides = build_bootstrap_overrides(
      "openai",
      "gpt-4o-mini",
      ConnectionChoice(use_api_key=True, api_key="sk-test123"),
    )
    assert overrides["backend.provider"] == "openai"
    assert overrides["backend.openai.model"] == "gpt-4o-mini"
    assert overrides["backend.openai.api_key"] == "sk-test123"

  def test_without_api_key(self) -> None:
    """OpenAI without API key only sets provider and model."""
    overrides = build_bootstrap_overrides(
      "openai", "gpt-4o-mini", ConnectionChoice(use_api_key=False)
    )
    assert overrides["backend.provider"] == "openai"
    assert overrides["backend.openai.model"] == "gpt-4o-mini"
    assert "backend.openai.api_key" not in overrides

  def test_no_base_url_override(self) -> None:
    """OpenAI never sets base_url (uses SDK default)."""
    overrides = build_bootstrap_overrides(
      "openai",
      "gpt-4o-mini",
      ConnectionChoice(use_api_key=True, api_key="sk-test123"),
    )
    assert "backend.openai.base_url" not in overrides


class TestBuildBootstrapOverridesAnthropic:
  """``build_bootstrap_overrides`` for Anthropic provider."""

  def test_with_api_key(self) -> None:
    """Anthropic with API key sets provider, model, and key."""
    overrides = build_bootstrap_overrides(
      "anthropic",
      "claude-3-5-sonnet-20241022",
      ConnectionChoice(use_api_key=True, api_key="sk-ant-test123"),
    )
    assert overrides["backend.provider"] == "anthropic"
    assert overrides["backend.anthropic.model"] == "claude-3-5-sonnet-20241022"
    assert overrides["backend.anthropic.api_key"] == "sk-ant-test123"

  def test_without_api_key(self) -> None:
    """Anthropic without API key only sets provider and model."""
    overrides = build_bootstrap_overrides(
      "anthropic", "claude-3-5-sonnet-20241022", ConnectionChoice(use_api_key=False)
    )
    assert overrides["backend.provider"] == "anthropic"
    assert overrides["backend.anthropic.model"] == "claude-3-5-sonnet-20241022"
    assert "backend.anthropic.api_key" not in overrides


class TestBuildBootstrapOverridesGemini:
  """``build_bootstrap_overrides`` for Gemini provider."""

  def test_with_api_key(self) -> None:
    """Gemini with API key sets provider, model, and key."""
    overrides = build_bootstrap_overrides(
      "gemini",
      "gemini-1.5-flash",
      ConnectionChoice(use_api_key=True, api_key="AIza-test123"),
    )
    assert overrides["backend.provider"] == "gemini"
    assert overrides["backend.gemini.model"] == "gemini-1.5-flash"
    assert overrides["backend.gemini.api_key"] == "AIza-test123"

  def test_without_api_key(self) -> None:
    """Gemini without API key only sets provider and model."""
    overrides = build_bootstrap_overrides(
      "gemini", "gemini-1.5-flash", ConnectionChoice(use_api_key=False)
    )
    assert overrides["backend.provider"] == "gemini"
    assert overrides["backend.gemini.model"] == "gemini-1.5-flash"
    assert "backend.gemini.api_key" not in overrides


class TestBuildBootstrapOverridesNone:
  """``build_bootstrap_overrides`` with no connection argument."""

  def test_no_connection_sets_provider_and_model_only(self) -> None:
    """When connection is None, only provider and model are set."""
    overrides = build_bootstrap_overrides("openai", "gpt-4o-mini", None)
    assert overrides["backend.provider"] == "openai"
    assert overrides["backend.openai.model"] == "gpt-4o-mini"
    assert "backend.openai.api_key" not in overrides
