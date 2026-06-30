"""Backend factory for creating ModelBackend instances.

Provides create_backend() factory function that instantiates the appropriate
backend based on configuration.

Architecture (dual backend):
  - Ollama: Native OllamaBackend (preserves web tools, native stats)
  - OpenAI/Anthropic/other: LitellmBackend (unified interface via litellm)

Security:
  - Validates base_url trust boundary before creating backend
  - Prevents credential leakage through malicious configs
"""

import os
from typing import TYPE_CHECKING

from yoker.backends.litellm import LitellmBackend
from yoker.backends.ollama import OllamaBackend
from yoker.backends.trust import validate_base_url_trust
from yoker.config import Config

if TYPE_CHECKING:
  from yoker.backends.protocol import ModelBackend


def create_backend(config: Config, interactive: bool | None = None) -> "ModelBackend":
  """Create a ModelBackend instance based on configuration.

  This is the recommended way to instantiate backend instances. The factory
  reads config.backend.provider and returns the appropriate backend.

  Architecture:
    - Ollama: Native OllamaBackend (full features: web tools, native stats)
    - OpenAI/Anthropic/others: LitellmBackend (unified interface via litellm)

  Security:
    - Validates base_url trust boundary before creating backend
    - Prevents credential leakage through malicious configs
    - Interactive mode: warns and asks for confirmation
    - Batch mode: requires YOKER_ALLOW_CUSTOM_BASE_URL=1

  Args:
    config: Yoker configuration object.
    interactive: Whether to show interactive prompts. If None, auto-detects
      from environment (YOKER_DEV_MODE or PYTEST_CURRENT_TEST).

  Returns:
    ModelBackend instance (OllamaBackend for 'ollama', LitellmBackend for others).

  Raises:
    ConfigurationError: If provider is unknown or not configured.
    TrustBoundaryError: If custom base_url is not allowed in batch mode.
  """
  # Auto-detect interactive mode from environment
  if interactive is None:
    interactive = (
      os.environ.get("YOKER_DEV_MODE") == "1"
      or not os.environ.get("PYTEST_CURRENT_TEST")
    )

  # Validate base_url trust boundary (all providers)
  validate_base_url_trust(config.backend, interactive=interactive)

  if config.backend.provider == "ollama":
    return OllamaBackend(config)

  return LitellmBackend(config)


__all__ = ["create_backend"]
