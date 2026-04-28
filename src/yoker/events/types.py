"""Event types for the Yoker event system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class EventType(Enum):
  """Enumeration of all event types."""

  # Session lifecycle
  SESSION_START = auto()
  SESSION_END = auto()

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

  # Command execution
  COMMAND = auto()

  # Error
  ERROR = auto()


@dataclass(frozen=True, kw_only=True)
class Event:
  """Base event class with common fields."""

  type: EventType
  timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SessionStartEvent(Event):
  """Emitted when agent session starts."""

  model: str
  thinking_enabled: bool
  config_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionEndEvent(Event):
  """Emitted when agent session ends."""

  reason: str  # "quit", "error", "interrupt"


@dataclass(frozen=True)
class TurnStartEvent(Event):
  """Emitted when processing a user message begins."""

  message: str


@dataclass(frozen=True)
class TurnEndEvent(Event):
  """Emitted when processing a user message completes."""

  response: str
  tool_calls_count: int = 0
  # Token statistics (from Ollama response)
  prompt_eval_count: int = 0
  eval_count: int = 0
  # Duration in milliseconds
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
  """Emitted for each chunk of content output."""

  text: str


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
class ErrorEvent(Event):
  """Emitted when an error occurs."""

  error_type: str
  message: str
  details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandEvent(Event):
  """Emitted when a slash command is executed."""

  command: str  # The command string (e.g., "/help")
  result: str  # The command output
