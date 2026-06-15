"""Context manager interface and data structures.

Defines the ContextStatistics dataclass for pluggable context management
implementations. The ContextManager base class lives in
:mod:`yoker.context.manager`.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ContextStatistics:
  """Statistics about context usage.

  Attributes:
    message_count: Total number of messages in context.
    turn_count: Total number of conversation turns.
    tool_call_count: Total number of tool calls.
    start_time: When the session started.
    last_turn_time: When the last turn completed (None if no turns).
  """

  message_count: int = 0
  turn_count: int = 0
  tool_call_count: int = 0
  start_time: datetime = field(default_factory=datetime.now)
  last_turn_time: datetime | None = None


@dataclass(frozen=True)
class SessionMetadata:
  """Metadata about a stored session.

  Attributes:
    session_id: Unique session identifier.
    start_time: When the session started.
    last_turn_time: When the last turn completed (None if no turns).
    message_count: Total number of messages.
    turn_count: Total number of conversation turns.
    last_message: Preview of the last message (truncated to 100 chars).
    file_path: Path to the session file.
  """

  session_id: str
  start_time: datetime
  last_turn_time: datetime | None = None
  message_count: int = 0
  turn_count: int = 0
  last_message: str = ""
  file_path: str = ""


__all__ = [
  "ContextStatistics",
  "SessionMetadata",
]
