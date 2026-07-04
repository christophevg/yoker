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
# :class:`SessionEvent` envelope wrapping an agent-emitted event
# (MBI-007, PR #43 Clarification 9). The union is deferred to a string
# forward reference to avoid a circular import with ``session_event``.
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

  # Session lifecycle (MBI-007)
  SESSION_START = auto()
  SESSION_END = auto()
  AGENT_SPAWNED = auto()
  AGENT_FINISHED = auto()
  AGENT_MESSAGE = auto()


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
  # Duration in milliseconds (Ollama-native)
  total_duration_ms: int = 0


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
    operation: Operation type (e.g., "write", "replace", "insert_before", "insert_after", "delete").
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
  """Emitted when a Session starts (MBI-007).

  Attributes:
    session_id: The unique session identifier.
  """

  session_id: str


@dataclass(frozen=True)
class SessionEndEvent(Event):
  """Emitted when a Session ends (MBI-007).

  Attributes:
    session_id: The unique session identifier.
  """

  session_id: str


@dataclass(frozen=True)
class AgentSpawnedEvent(Event):
  """Emitted when an agent is spawned into a Session (MBI-007).

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
  """Emitted when an agent finishes in a Session (MBI-007).

  This is a lifecycle signal; the agent is removed from the Session's
  active list after this event is emitted (PR #43 Clarification 7).

  Attributes:
    session_id: The session that owned the agent.
    agent_id: The unique session-assigned id of the finished agent.
  """

  session_id: str
  agent_id: str


@dataclass(frozen=True)
class AgentMessageEvent(Event):
  """Emitted when an inter-agent message is routed through a Session (MBI-007).

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
