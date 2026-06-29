"""Backend factory for creating ModelBackend instances.

Provides create_backend() factory function that instantiates the appropriate
backend based on configuration.
"""

from typing import TYPE_CHECKING

from yoker.backends.ollama import OllamaBackend
from yoker.config import BackendConfig, Config
from yoker.exceptions import ConfigurationError

if TYPE_CHECKING:
  from yoker.backends.protocol import ModelBackend


def create_backend(config: Config) -> "ModelBackend":
  """Create a ModelBackend instance based on configuration.

  This is the recommended way to instantiate backend instances. The factory
  reads config.backend.provider and returns the appropriate backend.

  For Phase 1, only 'ollama' is fully implemented. Other providers are
  recognized but will raise NotImplementedError.

  Args:
    config: Yoker configuration object.

  Returns:
    ModelBackend instance (OllamaBackend for provider='ollama').

  Raises:
    ConfigurationError: If provider is unknown or not configured.
    NotImplementedError: If provider is known but not yet implemented.
  """
  backend_config: BackendConfig = config.backend
  provider = backend_config.provider

  if provider == "ollama":
    # Import AsyncClient here to avoid hard dependency for other providers
    from ollama import AsyncClient

    # Create AsyncClient with ollama-specific config
    ollama_config = backend_config.ollama
    client = AsyncClient(
      host=ollama_config.base_url,
      timeout=ollama_config.timeout_seconds,
    )
    # Note: Ollama AsyncClient doesn't have an api_key parameter yet,
    # but we track it in config for future use
    return OllamaBackend(client)

  if provider == "openai":
    # Phase 2 will implement OpenAI backend
    raise NotImplementedError(
      "OpenAI backend not implemented. OpenAI backend will be implemented in Phase 2."
    )

  if provider == "anthropic":
    # Phase 3 will implement Anthropic backend
    raise NotImplementedError(
      "Anthropic backend not implemented. Anthropic backend will be implemented in Phase 3."
    )

  # Unknown provider
  raise ConfigurationError(
    setting="backend.provider",
    message=f"Unknown provider: {provider}. Supported providers: ollama, openai, anthropic",
  )


__all__ = ["create_backend"]
