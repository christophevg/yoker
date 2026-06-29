"""ModelBackend Protocol and streaming types.

Provides provider-neutral backend interface and streaming chunk types.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol


class ChatChunkEvent(Enum):
  """Event kind for a ChatChunk.

  Exactly one event kind is set per chunk. Backends emit a sequence of
  events following a specific order:
  - CONTENT_START/THINKING_START before first delta
  - CONTENT_DELTA/THINKING_DELTA for text chunks
  - TOOL_CALL_START/DELTA/STOP per tool call
  - USAGE when stats are available
  - DONE as terminal event
  """

  CONTENT_START = auto()  # Content block opened (Anthropic content_block_start type=text)
  CONTENT_DELTA = auto()  # Text delta
  CONTENT_STOP = auto()  # Content block closed
  THINKING_START = auto()  # Thinking block opened (Anthropic content_block_start type=thinking)
  THINKING_DELTA = auto()  # Thinking text delta
  THINKING_STOP = auto()  # Thinking block closed
  TOOL_CALL_START = auto()  # Tool use block opened (Anthropic) / first tool delta (delta-style)
  TOOL_CALL_DELTA = auto()  # Arguments JSON delta
  TOOL_CALL_STOP = auto()  # Tool use block closed (Anthropic; synthesised by delta-style backends)
  USAGE = auto()  # Usage/stats available (may arrive before final DONE)
  DONE = auto()  # Stream complete


@dataclass(frozen=True)
class ToolCallDelta:
  """Incremental tool-call fragment, provider-agnostic.

  Attributes:
    index: Block index (Anthropic) or positional identifier (OpenAI/Ollama).
      Used to associate START/DELTA/STOP for the same call.
    id: Tool call id. Set on START when available (OpenAI/Anthropic provide it
      up front; Ollama may synthesise one on STOP).
    name: Tool name. Set on START (OpenAI/Anthropic) or on the first delta
      that carries it (Ollama).
    arguments_delta: JSON fragment of the arguments being streamed. Empty
      string deltas are possible.
  """

  index: int
  id: str | None = None
  name: str | None = None
  arguments_delta: str | None = None


@dataclass(frozen=True)
class UsageStats:
  """Token/duration stats, provider-agnostic.

  Ollama-native fields are kept first-class so native stats are preserved.
  OpenAI/Anthropic map to input_tokens/output_tokens.
  """

  input_tokens: int | None = None  # OpenAI/Anthropic
  output_tokens: int | None = None  # OpenAI/Anthropic
  prompt_eval_count: int | None = None  # Ollama native (== input_tokens)
  eval_count: int | None = None  # Ollama native (== output_tokens)
  total_duration_ms: int | None = None  # Ollama native total duration


@dataclass(frozen=True)
class ChatChunk:
  """A single neutral chunk emitted by a ModelBackend stream.

  Exactly one of ``text`` / ``tool_call`` / ``usage`` is set depending on
  ``event``; the others are ``None``.
  """

  event: ChatChunkEvent
  index: int | None = None  # Block index for block-style providers
  text: str | None = None  # Text delta for CONTENT_DELTA / THINKING_DELTA
  tool_call: ToolCallDelta | None = None  # For TOOL_CALL_* events
  usage: UsageStats | None = None  # For USAGE / DONE


class ModelBackend(Protocol):
  """Provider-neutral streaming chat backend."""

  @property
  def provider(self) -> str:
    """Provider id, e.g. 'ollama' | 'openai' | 'anthropic'."""
    ...

  def chat_stream(
    self,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    think: bool = False,
    **kwargs: Any,
  ) -> AsyncIterator[ChatChunk]:
    """Stream a chat completion as a sequence of ChatChunk.

    Implementations MUST emit CONTENT_START before the first CONTENT_DELTA,
    a final USAGE (when available), and a terminal DONE. TOOL_CALL_START/
    DELTA/STOP bracket each tool call. Backends that do not natively signal
    block boundaries (Ollama, OpenAI) synthesise them.

    Args:
      model: Model identifier (provider-specific).
      messages: Conversation messages (OpenAI-style format).
      tools: Tool definitions (OpenAI function schema format).
      think: Enable thinking/reasoning mode (provider-specific behavior).
      **kwargs: Internal use only - per-provider parameters live in config,
        not call-site kwargs.

    Yields:
      ChatChunk instances representing streaming events.

    Note:
      The ``**kwargs`` parameter is purely internal - backends consume their
      own ``Parameters`` config and ignore unknown kwargs. It is not a stable
      public extension point; per-provider parameters live in config, not in
      call-site kwargs.
    """
    ...
