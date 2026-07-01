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
    description="Cloud inference with free tier (no local download required)",
    requires_api_key=False,  # Can use app without key
    has_local_app=True,
    account_url=f"{DOCS_BASE_URL}/getting-started-with-ollama.html#account",
    api_key_url=f"{DOCS_BASE_URL}/getting-started-with-ollama.html#api-key",
    docs_guide_url=f"{DOCS_BASE_URL}/getting-started-with-ollama.html",
    curated_models=[
      CuratedModel(
        model_id="qwen3.5:cloud",
        label="Qwen 3.5 Cloud (default)",
        note="fast cloud model, excellent tool calling and reasoning",
      ),
      CuratedModel(
        model_id="glm-5:cloud",
        label="GLM-5 Cloud",
        note="capable cloud model with strong coding abilities",
      ),
      CuratedModel(
        model_id="kimi-k2.6:cloud",
        label="Kimi K2.6 Cloud",
        note="advanced cloud model with large context window",
      ),
      CuratedModel(
        model_id="gemma4:31b-cloud",
        label="Gemma 4 31B Cloud",
        note="larger cloud model for complex reasoning tasks",
      ),
    ],
    default_model="qwen3.5:cloud",
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
        note="fast, affordable, excellent for most tasks",
      ),
      CuratedModel(
        model_id="gpt-5.4-mini",
        label="GPT-5.4 Mini",
        note="strongest mini model for coding and computer use",
      ),
      CuratedModel(
        model_id="gpt-4.1",
        label="GPT-4.1",
        note="smartest non-reasoning model",
      ),
      CuratedModel(
        model_id="gpt-5.4",
        label="GPT-5.4",
        note="affordable frontier model for professional work",
      ),
      CuratedModel(
        model_id="gpt-5.5",
        label="GPT-5.5",
        note="latest flagship for coding and complex reasoning",
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
        model_id="claude-haiku-4-5",
        label="Claude Haiku 4.5 (default)",
        note="fastest with near-frontier intelligence",
      ),
      CuratedModel(
        model_id="claude-sonnet-5",
        label="Claude Sonnet 5",
        note="best speed/intelligence balance, adaptive thinking",
      ),
      CuratedModel(
        model_id="claude-opus-4-8",
        label="Claude Opus 4.8",
        note="most capable Opus-tier for complex reasoning",
      ),
      CuratedModel(
        model_id="claude-fable-5",
        label="Claude Fable 5",
        note="most capable widely released model",
      ),
    ],
    default_model="claude-haiku-4-5",
  ),
  "gemini": ProviderInfo(
    id="gemini",
    display_name="Google Gemini",
    description="Gemini models via Google AI API (free tier available, works with your Google account)",
    requires_api_key=True,
    has_local_app=False,
    account_url=f"{DOCS_BASE_URL}/getting-started-with-gemini.html#account",
    api_key_url=f"{DOCS_BASE_URL}/getting-started-with-gemini.html#api-key",
    docs_guide_url=f"{DOCS_BASE_URL}/getting-started-with-gemini.html",
    curated_models=[
      CuratedModel(
        model_id="gemini-2.5-flash-lite",
        label="Gemini 2.5 Flash-Lite (default)",
        note="fastest, most budget-friendly model",
      ),
      CuratedModel(
        model_id="gemini-2.5-flash",
        label="Gemini 2.5 Flash",
        note="best price-performance ratio, excellent for reasoning",
      ),
      CuratedModel(
        model_id="gemini-2.5-pro",
        label="Gemini 2.5 Pro",
        note="most advanced for complex tasks and deep reasoning",
      ),
      CuratedModel(
        model_id="gemini-3.5-flash",
        label="Gemini 3.5 Flash",
        note="most intelligent for agentic and coding tasks",
      ),
      CuratedModel(
        model_id="gemini-3.1-pro-preview",
        label="Gemini 3.1 Pro Preview",
        note="advanced reasoning, preview release",
      ),
    ],
    default_model="gemini-2.5-flash-lite",
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


# NOTE ON MODEL COMPATIBILITY:
# The curated models above have been tested and verified to work well with yoker's
# tool calling features. Other models from these providers may also work but have
# not been officially tested. Some known limitations:
#
# Ollama:
#   - Gemma 3: Lacks native tool calling support (community workarounds unreliable)
#   - Gemini 3 via Ollama Cloud: Has thought_signature issues with multi-turn tool calling
#   - Models smaller than 7B parameters: May struggle with complex tool scenarios
#
# Provider-specific model lists change frequently. Check the official documentation:
#   - OpenAI: https://developers.openai.com/api/docs/models/all
#   - Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview
#   - Gemini: https://ai.google.dev/gemini-api/docs/models
#   - Ollama: https://ollama.com/models (look for "tools" badge)

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
