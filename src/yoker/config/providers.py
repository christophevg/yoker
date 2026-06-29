"""Provider configuration classes for Yoker.

This module contains configuration classes for all supported LLM providers.
The classes are structured to align with litellm conventions for easy integration.

Provider Configuration Pattern:
  Each provider has:
    - A Parameters class (model generation parameters)
    - A Config class (provider-specific configuration)

  The Parameters class contains model-level settings like temperature, top_p, etc.
  The Config class contains provider-level settings like API key, base URL, model name.

Supported Providers:
  - Ollama: Local inference server
  - OpenAI: GPT models (and compatible APIs)
  - Anthropic: Claude models
  - Gemini: Google Gemini models (via litellm)

All providers except Ollama are handled via litellm, which supports 100+ providers.
"""

from dataclasses import dataclass, field
from typing import Union

from yoker.config.validators import (
  validate_choice,
  validate_non_empty_string,
  validate_positive_int,
  validate_url,
)
from yoker.exceptions import ValidationError

# Type alias for provider configs (used for type hints)
ProviderConfig = Union["OllamaConfig", "OpenAIConfig", "AnthropicConfig", "GeminiConfig"]


@dataclass(frozen=True)
class OllamaParameters:
  """Ollama model parameters.

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    num_ctx: Context window size.
  """

  temperature: float = 0.7
  top_p: float = 0.9
  top_k: int = 40
  num_ctx: int = 4096

  def __post_init__(self) -> None:
    if not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.ollama.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.ollama.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    validate_positive_int(self.top_k, "backend.ollama.parameters.top_k")
    validate_positive_int(self.num_ctx, "backend.ollama.parameters.num_ctx")


@dataclass(frozen=True)
class OllamaConfig:
  """Ollama backend configuration.

  Attributes:
    base_url: URL of the Ollama API server.
    api_key: Optional API key for Ollama authorization.
    model: Default model to use.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  base_url: str = "http://localhost:11434"
  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "llama3.2:latest"
  timeout_seconds: int = 60
  parameters: OllamaParameters = field(default_factory=OllamaParameters)

  def __post_init__(self) -> None:
    validate_url(self.base_url, "backend.ollama.base_url")
    validate_non_empty_string(self.model, "backend.ollama.model")
    validate_positive_int(self.timeout_seconds, "backend.ollama.timeout_seconds")


@dataclass(frozen=True)
class OpenAIParameters:
  """OpenAI model parameters.

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    max_tokens: Maximum tokens in response.
  """

  temperature: float = 0.7
  top_p: float = 0.9
  max_tokens: int | None = None

  def __post_init__(self) -> None:
    if not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.openai.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.openai.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.max_tokens is not None:
      validate_positive_int(self.max_tokens, "backend.openai.parameters.max_tokens")


@dataclass(frozen=True)
class OpenAIConfig:
  """OpenAI backend configuration.

  Attributes:
    api_key: API key for OpenAI authorization.
    model: Default model to use.
    base_url: Optional base URL for OpenAI-compatible APIs.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
    reasoning_effort: Reasoning effort for o-series models ("low", "medium", or "high").
  """

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "gpt-4o-mini"
  base_url: str | None = None
  timeout_seconds: int = 60
  parameters: OpenAIParameters = field(default_factory=OpenAIParameters)
  reasoning_effort: str | None = None

  def __post_init__(self) -> None:
    validate_non_empty_string(self.model, "backend.openai.model")
    validate_positive_int(self.timeout_seconds, "backend.openai.timeout_seconds")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.openai.base_url")
    if self.reasoning_effort is not None:
      validate_choice(
        self.reasoning_effort,
        "backend.openai.reasoning_effort",
        ("low", "medium", "high"),
      )


@dataclass(frozen=True)
class AnthropicParameters:
  """Anthropic model parameters.

  Attributes:
    temperature: Sampling temperature (0.0-1.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    budget_tokens: Budget tokens for thinking (default 1024).
  """

  temperature: float = 0.7
  top_p: float = 0.9
  top_k: int | None = None
  budget_tokens: int = 1024

  def __post_init__(self) -> None:
    if not 0.0 <= self.temperature <= 1.0:
      raise ValidationError(
        "backend.anthropic.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 1.0",
      )
    if not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.anthropic.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.top_k is not None:
      validate_positive_int(self.top_k, "backend.anthropic.parameters.top_k")
    validate_positive_int(self.budget_tokens, "backend.anthropic.parameters.budget_tokens")


@dataclass(frozen=True)
class AnthropicConfig:
  """Anthropic backend configuration.

  Attributes:
    api_key: API key for Anthropic authorization.
    model: Default model to use.
    base_url: Optional base URL for Anthropic-compatible APIs.
    timeout_seconds: Request timeout in seconds.
    max_tokens: Maximum tokens in response (required by Anthropic API).
    parameters: Model generation parameters.
  """

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "claude-3-5-sonnet-20241022"
  base_url: str | None = None
  timeout_seconds: int = 60
  max_tokens: int = 4096
  parameters: AnthropicParameters = field(default_factory=AnthropicParameters)

  def __post_init__(self) -> None:
    validate_non_empty_string(self.model, "backend.anthropic.model")
    validate_positive_int(self.timeout_seconds, "backend.anthropic.timeout_seconds")
    validate_positive_int(self.max_tokens, "backend.anthropic.max_tokens")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.anthropic.base_url")


@dataclass(frozen=True)
class GeminiParameters:
  """Gemini model parameters.

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    max_output_tokens: Maximum tokens in response.
  """

  temperature: float = 0.7
  top_p: float = 0.9
  top_k: int | None = None
  max_output_tokens: int | None = None

  def __post_init__(self) -> None:
    if not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.gemini.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.gemini.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.top_k is not None:
      validate_positive_int(self.top_k, "backend.gemini.parameters.top_k")
    if self.max_output_tokens is not None:
      validate_positive_int(self.max_output_tokens, "backend.gemini.parameters.max_output_tokens")


@dataclass(frozen=True)
class GeminiConfig:
  """Gemini backend configuration.

  Attributes:
    api_key: API key for Google AI authorization.
    model: Default model to use (e.g., 'gemini-1.5-pro', 'gemini-1.5-flash').
    base_url: Optional base URL for Gemini-compatible APIs.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "gemini-1.5-flash"
  base_url: str | None = None
  timeout_seconds: int = 60
  parameters: GeminiParameters = field(default_factory=GeminiParameters)

  def __post_init__(self) -> None:
    validate_non_empty_string(self.model, "backend.gemini.model")
    validate_positive_int(self.timeout_seconds, "backend.gemini.timeout_seconds")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.gemini.base_url")


__all__ = [
  "ProviderConfig",
  "OllamaConfig",
  "OllamaParameters",
  "OpenAIConfig",
  "OpenAIParameters",
  "AnthropicConfig",
  "AnthropicParameters",
  "GeminiConfig",
  "GeminiParameters",
]
