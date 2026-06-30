"""Provider metadata for the bootstrap wizard.

This module holds provider-specific metadata (display names, URLs, curated models)
used by the multi-provider bootstrap wizard. The data-driven design allows adding
new providers without modifying wizard logic.

Provider metadata is the single source of truth for:
  - Provider display names and descriptions
  - Authentication requirements (API key vs app)
  - Documentation URLs (account setup, API key creation)
  - Curated model lists per provider
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedModel:
  """A single curated model entry.

  Attributes:
    model_id: The model identifier (e.g., 'gpt-4o-mini', 'claude-3-5-sonnet-20241022').
    label: Human-readable label shown in the wizard.
    note: Short helper note (e.g., 'fast and affordable').
  """

  model_id: str
  label: str
  note: str


@dataclass(frozen=True)
class ProviderInfo:
  """Metadata for a single LLM provider.

  Attributes:
    id: Internal provider identifier (e.g., 'ollama', 'openai').
    display_name: Human-readable name shown in the wizard (e.g., 'Ollama').
    description: One-line description for provider selection step.
    requires_api_key: Whether an API key is required (False for Ollama app path).
    has_local_app: Whether the provider has a local app option.
    account_url: URL to create an account (deep-link to docs).
    api_key_url: URL to create an API key (deep-link to docs).
    docs_guide_url: URL to the getting-started guide for this provider.
    curated_models: List of recommended models for this provider.
    default_model: Default model id for this provider.
  """

  id: str
  display_name: str
  description: str
  requires_api_key: bool
  has_local_app: bool
  account_url: str
  api_key_url: str | None
  docs_guide_url: str
  curated_models: list[CuratedModel]
  default_model: str


# Base URL for documentation guides
DOCS_BASE_URL = "https://yoker.readthedocs.io/en/latest/guides"


# Provider registry with all supported providers
PROVIDERS: dict[str, ProviderInfo] = {
  "ollama": ProviderInfo(
    id="ollama",
    display_name="Ollama",
    description="Local inference server with free cloud tier",
    requires_api_key=False,  # Can use app without key
    has_local_app=True,
    account_url=f"{DOCS_BASE_URL}/getting-started-with-ollama.html#account",
    api_key_url=f"{DOCS_BASE_URL}/getting-started-with-ollama.html#api-key",
    docs_guide_url=f"{DOCS_BASE_URL}/getting-started-with-ollama.html",
    curated_models=[
      CuratedModel(
        model_id="gemini-3-flash-preview:cloud",
        label="Gemini 3 Flash Preview (default)",
        note="cloud model, no local download needed",
      ),
      CuratedModel(
        model_id="gpt-oss:20b",
        label="gpt-oss:20b",
        note="cloud model, larger reasoning model",
      ),
      CuratedModel(
        model_id="llama3.1:8b",
        label="Llama 3.1 8B",
        note="local model, requires `ollama pull llama3.1:8b`",
      ),
      CuratedModel(
        model_id="qwen2.5:7b",
        label="Qwen 2.5 7B",
        note="local model, requires `ollama pull qwen2.5:7b`",
      ),
    ],
    default_model="gemini-3-flash-preview:cloud",
  ),
  "openai": ProviderInfo(
    id="openai",
    display_name="OpenAI",
    description="GPT models via OpenAI API",
    requires_api_key=True,
    has_local_app=False,
    account_url=f"{DOCS_BASE_URL}/getting-started-with-openai.html#account",
    api_key_url=f"{DOCS_BASE_URL}/getting-started-with-openai.html#api-key",
    docs_guide_url=f"{DOCS_BASE_URL}/getting-started-with-openai.html",
    curated_models=[
      CuratedModel(
        model_id="gpt-4o-mini",
        label="GPT-4o Mini (default)",
        note="fast and affordable",
      ),
      CuratedModel(
        model_id="gpt-4o",
        label="GPT-4o",
        note="latest flagship model",
      ),
      CuratedModel(
        model_id="gpt-4-turbo",
        label="GPT-4 Turbo",
        note="high performance",
      ),
      CuratedModel(
        model_id="o1-preview",
        label="O1 Preview",
        note="reasoning model",
      ),
    ],
    default_model="gpt-4o-mini",
  ),
  "anthropic": ProviderInfo(
    id="anthropic",
    display_name="Anthropic",
    description="Claude models via Anthropic API",
    requires_api_key=True,
    has_local_app=False,
    account_url=f"{DOCS_BASE_URL}/getting-started-with-anthropic.html#account",
    api_key_url=f"{DOCS_BASE_URL}/getting-started-with-anthropic.html#api-key",
    docs_guide_url=f"{DOCS_BASE_URL}/getting-started-with-anthropic.html",
    curated_models=[
      CuratedModel(
        model_id="claude-3-5-sonnet-20241022",
        label="Claude 3.5 Sonnet (default)",
        note="balanced performance",
      ),
      CuratedModel(
        model_id="claude-3-5-haiku-20241022",
        label="Claude 3.5 Haiku",
        note="fast and efficient",
      ),
      CuratedModel(
        model_id="claude-3-opus-20240229",
        label="Claude 3 Opus",
        note="highest capability",
      ),
    ],
    default_model="claude-3-5-sonnet-20241022",
  ),
  "gemini": ProviderInfo(
    id="gemini",
    display_name="Google Gemini",
    description="Gemini models via Google AI API",
    requires_api_key=True,
    has_local_app=False,
    account_url=f"{DOCS_BASE_URL}/getting-started-with-gemini.html#account",
    api_key_url=f"{DOCS_BASE_URL}/getting-started-with-gemini.html#api-key",
    docs_guide_url=f"{DOCS_BASE_URL}/getting-started-with-gemini.html",
    curated_models=[
      CuratedModel(
        model_id="gemini-1.5-flash",
        label="Gemini 1.5 Flash (default)",
        note="fast and efficient",
      ),
      CuratedModel(
        model_id="gemini-1.5-pro",
        label="Gemini 1.5 Pro",
        note="balanced performance",
      ),
      CuratedModel(
        model_id="gemini-2.0-flash-exp",
        label="Gemini 2.0 Flash",
        note="experimental",
      ),
    ],
    default_model="gemini-1.5-flash",
  ),
}

# Ordered list of provider IDs for display in wizard (Ollama first for backward compat)
PROVIDER_ORDER: list[str] = ["ollama", "openai", "anthropic", "gemini"]


def get_provider_info(provider_id: str) -> ProviderInfo:
  """Get provider metadata by id.

  Args:
    provider_id: Provider identifier ('ollama', 'openai', 'anthropic', 'gemini').

  Returns:
    ProviderInfo for the provider.

  Raises:
    KeyError: If provider_id is not found.
  """
  return PROVIDERS[provider_id]


def get_default_provider() -> ProviderInfo:
  """Get the default provider (Ollama for backward compatibility).

  Returns:
    ProviderInfo for Ollama.
  """
  return PROVIDERS["ollama"]


def get_curated_models(provider_id: str) -> list[CuratedModel]:
  """Get curated models for a specific provider.

  Args:
    provider_id: Provider identifier ('ollama', 'openai', etc.)

  Returns:
    List of CuratedModel entries for the provider.
  """
  provider = get_provider_info(provider_id)
  return provider.curated_models


def get_default_model(provider_id: str) -> str:
  """Get the default model for a specific provider.

  Args:
    provider_id: Provider identifier.

  Returns:
    Default model id for the provider.
  """
  provider = get_provider_info(provider_id)
  return provider.default_model


__all__ = [
  "CuratedModel",
  "ProviderInfo",
  "PROVIDERS",
  "PROVIDER_ORDER",
  "get_provider_info",
  "get_default_provider",
  "get_curated_models",
  "get_default_model",
]
