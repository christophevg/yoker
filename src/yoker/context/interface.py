"""Context manager interface and data structures.

Defines the ContextManager protocol and ContextStatistics dataclass
for pluggable context management implementations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


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


@runtime_checkable
class ContextManager(Protocol):
  """Protocol for context management implementations.

  Context managers handle persistence of conversation history,
  tool results, and session state with secure storage.

  Note:
    File operations use atomic writes with file locking.
    In-memory operations are not thread-safe; use external
    synchronization if concurrent access is needed.
  """

  def get_session_id(self) -> str:
    """Get the unique session identifier.

    Returns:
      Session ID string (URL-safe base64).
    """
    ...

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
  ) -> None:
    """Add a message to the context.

    Args:
      role: Message role ("user", "assistant", "system").
      content: Message content.
      metadata: Optional metadata (e.g., images, files).
    """
    ...

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context.

    Args:
      tool_name: Name of the tool that was executed.
      tool_id: Unique identifier for the tool call.
      result: Tool execution result (typically JSON string).
      success: Whether the tool call succeeded.
    """
    ...

  def get_context(self) -> list[dict[str, Any]]:
    """Get the full context for backend submission.

    Returns:
      List of message dictionaries in Ollama format.
    """
    ...

  def get_messages(self) -> list[dict[str, Any]]:
    """Get all recorded messages.

    Returns:
      List of message dictionaries.
    """
    ...

  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn.

    Args:
      user_message: The user's message for this turn.
    """
    ...

  def end_turn(self, assistant_message: str) -> None:
    """End the current conversation turn.

    Args:
      assistant_message: The assistant's complete response.
    """
    ...

  def save(self) -> None:
    """Persist context to storage.

    Raises:
      ContextStorageError: If persistence fails.
    """
    ...

  def load(self) -> bool:
    """Load context from storage.

    Returns:
      True if context was loaded, False if no stored context exists.

    Raises:
      ContextCorruptionError: If stored context is corrupted.
    """
    ...

  def clear(self) -> None:
    """Clear in-memory context (does not delete from storage)."""
    ...

  def delete(self) -> None:
    """Delete stored context from disk.

    Raises:
      SessionNotFoundError: If session doesn't exist.
    """
    ...

  def get_statistics(self) -> ContextStatistics:
    """Get statistics about context usage.

    Returns:
      ContextStatistics dataclass instance.
    """
    ...

  def close(self) -> None:
    """Release resources and flush any pending writes."""
    ...


__all__ = [
  "ContextStatistics",
  "ContextManager",
]