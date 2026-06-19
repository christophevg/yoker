"""Base context manager implementation.

Provides ContextManager, a list-like base class for conversation history.
Subclasses can override :meth:`append` to add persistence or other side effects.
"""

from collections import UserList
from typing import Any

from yoker.context.interface import ContextStatistics


class ContextManager(UserList[dict[str, Any]]):
  """Base context manager - acts like a list.

  The Agent interacts with context through normal list operations such as
  :meth:`append`. Subclasses may override :meth:`append` to trigger
  persistence, compaction, or other lifecycle side effects.

  The internal list stores items in the format used by
  :meth:`get_context` and :meth:`get_messages`.
  """

  def __init__(self, initial: list[dict[str, Any]] | None = None) -> None:
    """Initialize the context manager.

    Args:
      initial: Optional initial list of context items.
    """
    super().__init__(initial)

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    thinking: str | None = None,
  ) -> None:
    """Add a message to the context.

    Args:
      role: Message role ("user", "assistant", "system").
      content: Message content.
      metadata: Optional metadata (e.g., images, files).
      thinking: Optional thinking/reasoning content (for assistant messages).
    """
    if not content:
      return
    message: dict[str, Any] = {
      "role": role,
      "content": content,
    }
    if metadata:
      message["metadata"] = metadata
    if thinking:
      message["thinking"] = thinking
    self.append(message)

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context."""
    self.append(
      {
        "role": "tool",
        "name": tool_name,
        "tool_id": tool_id,
        "content": result,
        "success": success,
      }
    )

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
  ) -> None:
    """Add an assistant message with tool calls to the context.

    This must be called BEFORE add_tool_result() for each tool call.

    Args:
      tool_calls: List of tool call dictionaries with 'name' and 'arguments'.
      thinking: Optional thinking/reasoning content from the assistant.
    """
    assistant_msg: dict[str, Any] = {
      "role": "assistant",
      "tool_calls": tool_calls,
      "content": "",
    }
    if thinking:
      assistant_msg["thinking"] = thinking
    self.append(assistant_msg)

  def get_context(self) -> list[dict[str, Any]]:
    """Get the full context for backend submission.

    Returns:
      List of message dictionaries in Ollama format.
    """
    return list(self.data)

  def get_messages(self) -> list[dict[str, Any]]:
    """Get all recorded messages (excludes tool results).

    Returns:
      List of message dictionaries.
    """
    return [item for item in self.data if item.get("role") != "tool"]

  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn."""
    self.add_message("user", user_message)

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    """End the current conversation turn.

    Args:
      assistant_message: The assistant's response content.
      thinking: Optional thinking/reasoning content from the assistant.
    """
    self.add_message("assistant", assistant_message, thinking=thinking)

  def save(self) -> None:
    """Persist context to storage.

    Subclasses may override this method. The base implementation is a no-op.
    """

  def load(self) -> bool:
    """Load context from storage.

    Returns:
      True if context was loaded, False if no stored context exists.
    """
    return False

  def delete(self) -> None:
    """Delete stored context from disk.

    Raises:
      NotImplementedError: By default; subclasses may override.
    """
    raise NotImplementedError("delete() not supported by this context manager")

  def get_statistics(self) -> ContextStatistics:
    """Get statistics about context usage."""
    message_count = sum(1 for item in self.data if item.get("role") != "tool")
    turn_count = sum(1 for item in self.data if item.get("role") == "user")

    return ContextStatistics(
      message_count=message_count,
      turn_count=turn_count,
      tool_call_count=0,
    )

  def close(self) -> None:
    """Release resources and flush any pending writes.

    The base implementation is a no-op.
    """

  def get_session_id(self) -> str:
    """Get the unique session identifier.

    Returns:
      Session ID string. Base implementation returns a fixed in-memory id.
    """
    return "in-memory"


__all__ = ["ContextManager"]
