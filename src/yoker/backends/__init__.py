"""Backends package - provider-neutral model backend protocol and types.

Provides:
  - ModelBackend: Protocol for streaming chat backends
  - ChatChunk: Provider-agnostic streaming chunk type
  - ChatChunkEvent: Event types for ChatChunk
  - ToolCallDelta: Incremental tool-call fragment
  - UsageStats: Token/duration statistics
  - create_backend: Factory function to create backend instances

This package defines the protocol that backends must implement.
Concrete backend implementations (OllamaBackend, OpenAIBackend, AnthropicBackend)
are in separate modules and are registered via the factory module.
"""

from yoker.backends.factory import create_backend
from yoker.backends.protocol import (
  ChatChunk,
  ChatChunkEvent,
  ModelBackend,
  ToolCallDelta,
  UsageStats,
)

__all__ = [
  "ModelBackend",
  "ChatChunk",
  "ChatChunkEvent",
  "ToolCallDelta",
  "UsageStats",
  "create_backend",
]
