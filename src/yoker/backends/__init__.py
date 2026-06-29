"""Backends package - provider-neutral model backend protocol and types.

Provides:
  - ModelBackend: Protocol for streaming chat backends
  - ChatChunk: Provider-agnostic streaming chunk type
  - ChatChunkEvent: Event types for ChatChunk
  - ToolCallDelta: Incremental tool-call fragment
  - UsageStats: Token/duration statistics
  - create_backend: Factory function to create backend instances
  - validate_base_url_trust: Trust boundary validation for custom endpoints

Architecture (dual backend):
  - OllamaBackend: Native Ollama SDK for full features (web tools, native stats)
  - LitellmBackend: Unified interface for OpenAI, Anthropic, and 100+ providers
"""

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

__all__ = [
  "ModelBackend",
  "ChatChunk",
  "ChatChunkEvent",
  "ToolCallDelta",
  "UsageStats",
  "create_backend",
  "OllamaBackend",
  "LitellmBackend",
  "validate_base_url_trust",
  "is_custom_base_url",
  "TrustBoundaryError",
  "DEFAULT_BASE_URLS",
  "ENV_ALLOW_CUSTOM_BASE_URL",
]
