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
from typing import ClassVar, Union

from yoker.config.validators import (
  validate_choice,
  validate_non_empty_string,
  validate_positive_int,
  validate_url,
)
from yoker.exceptions import ValidationError

# Type alias for provider configs (used for type hints)
ProviderConfig = Union[
  "OllamaConfig", "OpenAIConfig", "AnthropicConfig", "GeminiConfig", "GenericConfig"
]


@dataclass
class OllamaParameters:
  """Ollama model parameters.

  All parameters default to None to allow providers to use their own defaults.
  Ollama defaults: temperature=0.8, top_p=0.9, top_k=40, num_ctx=2048, num_predict=128

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    num_ctx: Context window size.
    num_predict: Maximum tokens to predict (maps from max_tokens).
    repeat_penalty: Repetition penalty (default 1.1).
    seed: Random seed for deterministic outputs.
  """

  temperature: float | None = None
  top_p: float | None = None
  top_k: int | None = None
  num_ctx: int | None = None
  num_predict: int | None = None
  repeat_penalty: float | None = None
  seed: int | None = None

  def __post_init__(self) -> None:
    if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.ollama.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if self.top_p is not None and not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.ollama.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.top_k is not None:
      validate_positive_int(self.top_k, "backend.ollama.parameters.top_k")
    if self.num_ctx is not None:
      validate_positive_int(self.num_ctx, "backend.ollama.parameters.num_ctx")
    if self.num_predict is not None:
      validate_positive_int(self.num_predict, "backend.ollama.parameters.num_predict")
    if self.repeat_penalty is not None and self.repeat_penalty <= 0.0:
      raise ValidationError(
        "backend.ollama.parameters.repeat_penalty",
        self.repeat_penalty,
        "must be positive",
      )


@dataclass
class OllamaConfig:
  """Ollama backend configuration.

  Attributes:
    base_url: URL of the Ollama API server.
    api_key: Optional API key for Ollama authorization.
    model: Default model to use.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  # Default base URLs for Ollama (localhost and cloud)
  DEFAULT_BASE_URLS: ClassVar[list[str] | None] = ["http://localhost:11434", "https://ollama.com"]

  base_url: str = field(
    default="http://localhost:11434",
    metadata={"help": "URL of the Ollama API server"},
  )
  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = field(
    default="qwen3.5:cloud",
    metadata={"help": "Default model to use"},
  )
  timeout_seconds: int = field(
    default=60,
    metadata={"help": "Request timeout in seconds"},
  )
  parameters: OllamaParameters = field(default_factory=OllamaParameters)

  def __post_init__(self) -> None:
    validate_url(self.base_url, "backend.ollama.base_url")
    validate_non_empty_string(self.model, "backend.ollama.model")
    validate_positive_int(self.timeout_seconds, "backend.ollama.timeout_seconds")


@dataclass
class OpenAIParameters:
  """OpenAI model parameters.

  All parameters default to None to allow providers to use their own defaults.
  OpenAI defaults: temperature=1.0, top_p=1.0

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    max_tokens: Maximum tokens in response.
    max_completion_tokens: Upper bound for tokens including reasoning (o-series).
    presence_penalty: Presence penalty (-2.0 to 2.0).
    frequency_penalty: Frequency penalty (-2.0 to 2.0).
    seed: Random seed for deterministic outputs.
    reasoning_effort: Reasoning intensity for o-series ("low", "medium", "high", "xhigh").
  """

  temperature: float | None = None
  top_p: float | None = None
  max_tokens: int | None = None
  max_completion_tokens: int | None = None
  presence_penalty: float | None = None
  frequency_penalty: float | None = None
  seed: int | None = None
  reasoning_effort: str | None = None

  def __post_init__(self) -> None:
    if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.openai.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if self.top_p is not None and not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.openai.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.max_tokens is not None:
      validate_positive_int(self.max_tokens, "backend.openai.parameters.max_tokens")
    if self.max_completion_tokens is not None:
      validate_positive_int(
        self.max_completion_tokens, "backend.openai.parameters.max_completion_tokens"
      )
    if self.presence_penalty is not None and not -2.0 <= self.presence_penalty <= 2.0:
      raise ValidationError(
        "backend.openai.parameters.presence_penalty",
        self.presence_penalty,
        "must be between -2.0 and 2.0",
      )
    if self.frequency_penalty is not None and not -2.0 <= self.frequency_penalty <= 2.0:
      raise ValidationError(
        "backend.openai.parameters.frequency_penalty",
        self.frequency_penalty,
        "must be between -2.0 and 2.0",
      )
    if self.reasoning_effort is not None:
      validate_choice(
        self.reasoning_effort,
        "backend.openai.parameters.reasoning_effort",
        ("low", "medium", "high", "xhigh"),
      )


@dataclass
class OpenAIConfig:
  """OpenAI backend configuration.

  Attributes:
    api_key: API key for OpenAI authorization.
    model: Default model to use.
    base_url: Optional base URL for OpenAI-compatible APIs.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  # No default base URLs - use SDK default
  DEFAULT_BASE_URLS: None = None

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "gpt-4o-mini"
  base_url: str | None = None
  timeout_seconds: int = 60
  parameters: OpenAIParameters = field(default_factory=OpenAIParameters)

  def __post_init__(self) -> None:
    validate_non_empty_string(self.model, "backend.openai.model")
    validate_positive_int(self.timeout_seconds, "backend.openai.timeout_seconds")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.openai.base_url")


@dataclass
class AnthropicParameters:
  """Anthropic model parameters.

  Note: max_tokens is REQUIRED by Anthropic API, so it must have a default.
  All other parameters default to None to allow providers to use their own defaults.
  Anthropic defaults: temperature=1.0, top_p=1.0

  Attributes:
    max_tokens: Maximum tokens in response (required by Anthropic API).
    temperature: Sampling temperature (0.0-1.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    budget_tokens: Budget tokens for thinking (default 1024).
    stop_sequences: Custom stop sequences.
  """

  max_tokens: int = 4096  # Required by Anthropic API
  temperature: float | None = None
  top_p: float | None = None
  top_k: int | None = None
  budget_tokens: int | None = None
  stop_sequences: list[str] | None = None

  def __post_init__(self) -> None:
    validate_positive_int(self.max_tokens, "backend.anthropic.parameters.max_tokens")
    if self.temperature is not None and not 0.0 <= self.temperature <= 1.0:
      raise ValidationError(
        "backend.anthropic.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 1.0",
      )
    if self.top_p is not None and not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.anthropic.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.top_k is not None:
      validate_positive_int(self.top_k, "backend.anthropic.parameters.top_k")
    if self.budget_tokens is not None:
      validate_positive_int(self.budget_tokens, "backend.anthropic.parameters.budget_tokens")


@dataclass
class AnthropicConfig:
  """Anthropic backend configuration.

  Attributes:
    api_key: API key for Anthropic authorization.
    model: Default model to use.
    base_url: Optional base URL for Anthropic-compatible APIs.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters (includes max_tokens).
  """

  # No default base URLs - use SDK default
  DEFAULT_BASE_URLS: None = None

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "claude-3-5-sonnet-20241022"
  base_url: str | None = None
  timeout_seconds: int = 60
  parameters: AnthropicParameters = field(default_factory=AnthropicParameters)

  def __post_init__(self) -> None:
    validate_non_empty_string(self.model, "backend.anthropic.model")
    validate_positive_int(self.timeout_seconds, "backend.anthropic.timeout_seconds")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.anthropic.base_url")


@dataclass
class GeminiParameters:
  """Gemini model parameters.

  All parameters default to None to allow providers to use their own defaults.

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    max_output_tokens: Maximum tokens in response.
    max_tokens: Alias for max_output_tokens.
    safety_settings: Content filtering thresholds.
  """

  temperature: float | None = None
  top_p: float | None = None
  top_k: int | None = None
  max_output_tokens: int | None = None
  max_tokens: int | None = None
  safety_settings: list[dict[str, str]] | None = None

  def __post_init__(self) -> None:
    if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.gemini.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if self.top_p is not None and not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.gemini.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.top_k is not None:
      validate_positive_int(self.top_k, "backend.gemini.parameters.top_k")
    if self.max_output_tokens is not None:
      validate_positive_int(self.max_output_tokens, "backend.gemini.parameters.max_output_tokens")
    if self.max_tokens is not None:
      validate_positive_int(self.max_tokens, "backend.gemini.parameters.max_tokens")


@dataclass
class GeminiConfig:
  """Gemini backend configuration.

  Attributes:
    api_key: API key for Google AI authorization.
    model: Default model to use (e.g., 'gemini-1.5-pro', 'gemini-1.5-flash').
    base_url: Optional base URL for Gemini-compatible APIs.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  # No default base URLs - use SDK default
  DEFAULT_BASE_URLS: None = None

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = "gemini-2.5-flash"
  base_url: str | None = None
  timeout_seconds: int = 60
  parameters: GeminiParameters = field(default_factory=GeminiParameters)

  def __post_init__(self) -> None:
    validate_non_empty_string(self.model, "backend.gemini.model")
    validate_positive_int(self.timeout_seconds, "backend.gemini.timeout_seconds")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.gemini.base_url")


@dataclass
class GenericParameters:
  """Generic provider parameters for unknown providers.

  Used as a catch-all for any litellm-supported provider not explicitly
  defined (e.g., 'groq', 'cohere', 'azure').

  All parameters default to None to allow providers to use their own defaults.
  """

  temperature: float | None = None
  top_p: float | None = None
  max_tokens: int | None = None

  def __post_init__(self) -> None:
    if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.generic.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if self.top_p is not None and not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.generic.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    if self.max_tokens is not None:
      validate_positive_int(self.max_tokens, "backend.generic.parameters.max_tokens")


@dataclass
class GenericConfig:
  """Generic provider configuration for unknown providers.

  Used as a catch-all for any litellm-supported provider not explicitly
  defined (e.g., 'groq', 'cohere', 'azure', 'mistral').

  Litellm handles the provider routing and authentication. The provider string
  should match litellm's expected format (e.g., 'groq/llama-3.1-8b-instant').

  Attributes:
    api_key: API key for the provider (optional, can also use environment variables).
    model: Default model to use (optional, can be specified in agent definition).
    base_url: Optional base URL for provider APIs.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  # No default base URLs - use SDK/provider defaults
  DEFAULT_BASE_URLS: None = None

  api_key: str | None = field(default=None, metadata={"cli": False})
  model: str = ""  # Optional - can come from agent definition
  base_url: str | None = None
  timeout_seconds: int = 60
  parameters: GenericParameters = field(default_factory=GenericParameters)

  def __post_init__(self) -> None:
    # model is optional for GenericConfig - can be specified in agent definition
    if self.model:  # Only validate if model is provided
      validate_non_empty_string(self.model, "backend.generic.model")
    validate_positive_int(self.timeout_seconds, "backend.generic.timeout_seconds")
    if self.base_url is not None:
      validate_url(self.base_url, "backend.generic.base_url")


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
  "GenericConfig",
  "GenericParameters",
]
