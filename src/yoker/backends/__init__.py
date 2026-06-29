"""Backends package - provider-neutral model backend protocol and types.

Provides:
  - ModelBackend: Protocol for streaming chat backends
  - ChatChunk: Provider-agnostic streaming chunk type
  - ChatChunkEvent: Event types for ChatChunk
  - ToolCallDelta: Incremental tool-call fragment
  - UsageStats: Token/duration statistics
  - create_backend: Factory function to create backend instances
  - with_model: Helper to create a copy of backend config with overridden model
  - validate_base_url_trust: Trust boundary validation for custom endpoints

Architecture (dual backend):
  - OllamaBackend: Native Ollama SDK for full features (web tools, native stats)
  - LitellmBackend: Unified interface for OpenAI, Anthropic, and 100+ providers
"""

from dataclasses import replace
from typing import TYPE_CHECKING

from yoker.backends.factory import create_backend
from yoker.backends.litellm import LitellmBackend
from yoker.backends.ollama import OllamaBackend
from yoker.backends.protocol import (
  ChatChunk,
  ChatChunkEvent,
  ModelBackend,
  ToolCallDelta,
  UsageStats,
)
from yoker.backends.trust import (
  DEFAULT_BASE_URLS,
  ENV_ALLOW_CUSTOM_BASE_URL,
  TrustBoundaryError,
  is_custom_base_url,
  validate_base_url_trust,
)

if TYPE_CHECKING:
  from yoker.config import BackendConfig


def with_model(backend: "BackendConfig", model: str) -> "BackendConfig":
  """Return a copy of backend config with model overridden on the active sub-config.

  This is a provider-agnostic helper that works for any provider's sub-config.
  Used by subagent spawn to copy the parent's backend config with a different model.

  Args:
    backend: The backend configuration to copy.
    model: The new model to use.

  Returns:
    A new BackendConfig with the model overridden on the active provider's sub-config.

  Raises:
    ValueError: If no config is available for the active provider.
  """
  # Get the active provider's config using the generic property
  sub_config = backend.config
  if sub_config is None:
    raise ValueError(f"No config for provider: {backend.provider}")

  # Override model on the sub-config
  new_sub_config = replace(sub_config, model=model)

  # Return new BackendConfig with updated sub-config
  return replace(backend, **{backend.provider: new_sub_config})


__all__ = [
  "ModelBackend",
  "ChatChunk",
  "ChatChunkEvent",
  "ToolCallDelta",
  "UsageStats",
  "create_backend",
  "with_model",
  "OllamaBackend",
  "LitellmBackend",
  "validate_base_url_trust",
  "is_custom_base_url",
  "TrustBoundaryError",
  "DEFAULT_BASE_URLS",
  "ENV_ALLOW_CUSTOM_BASE_URL",
]

