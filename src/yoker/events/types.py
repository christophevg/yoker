"""Event types for the Yoker event system."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.events.session_event import SessionEvent

# Handlers accept either a bare :class:`Event` (single-agent path) or a
# :class:`SessionEvent` envelope wrapping an agent-emitted event. The
# union is deferred to a string forward reference to avoid a circular
# import with ``session_event``.
EventCallback = (
  Callable[["Event | SessionEvent"], None]
  | Callable[["Event | SessionEvent"], Coroutine[None, None, None]]
)


class EventType(Enum):
  """Enumeration of all event types."""

  # Turn lifecycle
  TURN_START = auto()
  TURN_END = auto()

  # Thinking (reasoning trace)
  THINKING_START = auto()
  THINKING_CHUNK = auto()
  THINKING_END = auto()

  # Content (response text)
  CONTENT_START = auto()
  CONTENT_CHUNK = auto()
  CONTENT_END = auto()

  # Tool execution
  TOOL_CALL = auto()
  TOOL_RESULT = auto()
  TOOL_CONTENT = auto()  # Content display event for write/update tools

  # Command execution
  COMMAND = auto()

  # Session lifecycle
  SESSION_START = auto()
  SESSION_END = auto()
  AGENT_SPAWNED = auto()
  AGENT_FINISHED = auto()
  AGENT_MESSAGE = auto()

  # Context management
  CONTEXT_OVERFLOW = auto()

  # Agent health
  AGENT_TIMEOUT = auto()


@dataclass(frozen=True, kw_only=True)
class Event:
  """Base event class with common fields."""

  type: EventType
  timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class TurnStartEvent(Event):
  """Emitted when processing a user message begins."""

  message: str


@dataclass(frozen=True)
class TurnEndEvent(Event):
  """Emitted when processing a user message completes."""

  response: str
  tool_calls_count: int = 0
  # Provider-neutral token statistics (OpenAI/Anthropic)
  input_tokens: int = 0
  output_tokens: int = 0
  # Ollama-native token statistics
  prompt_eval_count: int = 0
  eval_count: int = 0
  # Duration in milliseconds (wall-clock, provider-independent)
  total_duration_ms: int = 0
  # API usage limits from the backend (Ollama cloud usage API)
  usage_limits: dict[str, Any] | None = None


@dataclass(frozen=True)
class ThinkingStartEvent(Event):
  """Emitted when thinking output begins."""

  pass


@dataclass(frozen=True)
class ThinkingChunkEvent(Event):
  """Emitted for each chunk of thinking output."""

  text: str


@dataclass(frozen=True)
class ThinkingEndEvent(Event):
  """Emitted when thinking output ends."""

  total_length: int


@dataclass(frozen=True)
class ContentStartEvent(Event):
  """Emitted when content output begins."""

  pass


@dataclass(frozen=True)
class ContentChunkEvent(Event):
  """Emitted for each chunk of content output.

  Attributes:
    text: The content text chunk.
    content_type: MIME type of the content (default: "text/plain").
      Possible values: "text/plain", "text/markdown", "text/html", etc.
  """

  text: str
  content_type: str = "text/plain"


@dataclass(frozen=True)
class ContentEndEvent(Event):
  """Emitted when content output ends."""

  total_length: int


@dataclass(frozen=True)
class ToolCallEvent(Event):
  """Emitted when a tool is called."""

  tool_name: str
  arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResultEvent(Event):
  """Emitted when a tool returns a result."""

  tool_name: str
  result: str
  success: bool = True


@dataclass(frozen=True)
class ToolContentEvent(Event):
  """Emitted when a tool has content to display (write/update operations).

  Attributes:
    tool_name: Name of the tool (e.g., "write", "update").
    operation: Operation type (e.g., "write", "replace", "insert", "append", "delete").
    path: Resolved file path.
    content_type: MIME type of the content. Common values:
      - "text/plain": Plain text content (default)
      - "text/x-diff": Unified diff format
      - "application/json": JSON data
      - "text/markdown": Markdown content
      - "application/x-summary": Custom type indicating operation summary only (no content field)
    content: Content to display (truncated if too large, None for summary type).
    metadata: Additional metadata (lines, bytes, is_new_file, is_overwrite, etc.).
  """

  tool_name: str
  operation: str
  path: str
  content_type: str
  content: str | None = None
  metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandEvent(Event):
  """Emitted when a slash command is executed."""

  command: str  # The command string (e.g., "/help")
  result: str  # The command output


@dataclass(frozen=True)
class SessionStartEvent(Event):
  """Emitted when a Session starts.

  Attributes:
    session_id: The unique session identifier.
  """

  session_id: str


@dataclass(frozen=True)
class SessionEndEvent(Event):
  """Emitted when a Session ends.

  Attributes:
    session_id: The unique session identifier.
  """

  session_id: str


@dataclass(frozen=True)
class AgentSpawnedEvent(Event):
  """Emitted when an agent is spawned into a Session.

  Attributes:
    session_id: The session that owns the spawned agent.
    agent_id: The unique session-assigned id of the spawned agent.
    definition_name: The agent definition name the agent was created from.
  """

  session_id: str
  agent_id: str
  definition_name: str


@dataclass(frozen=True)
class AgentFinishedEvent(Event):
  """Emitted when an agent finishes in a Session.

  This is a lifecycle signal; the agent is removed from the Session's
  active list after this event is emitted.

  Attributes:
    session_id: The session that owned the agent.
    agent_id: The unique session-assigned id of the finished agent.
  """

  session_id: str
  agent_id: str


@dataclass(frozen=True)
class AgentMessageEvent(Event):
  """Emitted when an inter-agent message is routed through a Session.

  Attributes:
    session_id: The session routing the message.
    from_id: The unique id of the sending agent.
    to_id: The unique id of the receiving agent.
    content: The plain-string message content.
  """

  session_id: str
  from_id: str
  to_id: str
  content: str


@dataclass(frozen=True)
class ContextOverflowEvent(Event):
  """Emitted once when context overflow compaction fires.

  Audit trail for the framework-default context management: the size check
  estimated the conversation had grown past ``context.max_tokens`` and the
  compaction pipeline flagged/stubbed older non-setup messages to bring
  the submitted view back under the trim target.

  Stored-vs-sent semantics: ``message_count`` and ``dropped_count``
  describe the STORED history (all messages kept on disk, including
  stubbed ones and — with flag-based compaction — the bodies hidden from
  the view); ``sent_count`` is what the NEXT submission actually contains
  after the projection applied every flag.

  Attributes:
    message_count: Number of messages in the stored context after the
      pipeline (compaction keeps stored messages — flags only change the
      view; a cutoff-flagged message remains in the store too, so this
      no longer decreases with flag-based compaction).
    estimated_tokens: The estimated token count that triggered overflow.
    max_tokens: The configured soft cap (``context.max_tokens``).
    dropped_count: Number of messages newly cut-off-flagged by the
      pipeline (stored-based; legacy meaning "permanently removed").
    first_remaining: One-line summary of the first non-protected message
      after compaction (where retained history starts), or None when only
      the protected prefix remains.
    target_tokens: The effective trim target in tokens
      (``max_tokens * context.compact_ratio``), i.e. the goal the
      pipeline trimmed toward. None when the event was produced by older
      code without hysteresis (deserialization of historical JSONL records).
    stages: Per-stage impact, ONLY stages with non-zero impact, in run
      order: ``{"name": str, "messages": int, "tokens": int}`` where
      ``tokens`` is the view-estimate reduction attributable to the stage
      (estimate before → after that stage). Empty for events produced by
      older code.
    sent_count: Number of messages in the submitted view
      (``get_context()``) after the pipeline — i.e. what the model will
      actually see. None for events produced by older code.
    remaining_estimated_tokens: The ACHIEVED post-pipeline view estimate
      (the truthfulness fix: the old panel showed the TARGET, not the
      result). None for events produced by older code.
    run_id: This compaction run's id (8-hex) — flags carry it in their
      ``pruned.run`` metadata, so per-run reporting can count THIS run's
      messages. None for events produced by older code.
    floor_tokens: Calibrated estimate of the PROTECTED VIEW — the floor
      the cutoff target can never be clamped below. None when no clamp
      was needed/older code.
    target_clamped: True when the effective cutoff target was raised to
      the floor because the protected content alone exceeds the ratio
      target (the pipeline then aims at the floor).
  """

  message_count: int
  estimated_tokens: int
  max_tokens: int
  dropped_count: int
  first_remaining: str | None = None
  target_tokens: int | None = None
  stages: list[dict[str, Any]] = field(default_factory=list)
  sent_count: int | None = None
  remaining_estimated_tokens: int | None = None
  run_id: str | None = None
  floor_tokens: int | None = None
  target_clamped: bool = False


@dataclass(frozen=True)
class TimeoutEvent(Event):
  """Emitted when the idle watchdog kills the agent's LLM streaming.

  The agent's idle watchdog detects that the LLM backend has not produced
  any data (content chunks, thinking, tool calls) for ``timeout_seconds``
  consecutive seconds during the streaming phase. The watchdog cancels
  the in-flight ``_consume_stream`` call, emits this event, and raises
  ``TimeoutError`` to the ``process()`` caller. The agent stays alive —
  the caller can retry with another ``process()`` call.

  Attributes:
    idle_seconds: How long the agent was idle before the timeout fired.
    timeout_seconds: The configured idle-timeout threshold.
  """

  idle_seconds: float
  timeout_seconds: int
