"""Base context manager implementation.

Provides BaseContextManager, the in-memory base for conversation history.
Subclasses (SimpleContextManager) can override setup_initial_context to
add richer initial context. Wrappers (ContextManagerWrapper, Persisted)
forward to a wrapped instance instead.
"""

from typing import TYPE_CHECKING, Any

from structlog import get_logger

from yoker.context.interface import ContextStatistics

if TYPE_CHECKING:
  from yoker.core import Agent

logger = get_logger(__name__)


class BaseContextManager:
  """In-memory base context manager.

  Stores messages in an internal list. The list surface (UserList, append,
  data, __getitem__, __len__, __iter__) is removed — callers use
  get_messages() / get_context() / the adder methods.
  """

  def __init__(self, initial: list[dict[str, Any]] | None = None) -> None:
    """Initialize the context manager.

    Args:
      initial: Optional initial list of context items.
    """
    self._agent: Agent | None = None
    self._messages: list[dict[str, Any]] = list(initial) if initial else []

  @property
  def agent(self) -> "Agent | None":
    return self._agent

  @agent.setter
  def agent(self, new_agent: "Agent") -> None:
    self._agent = new_agent
    self.clear()
    self.setup_initial_context()
    self.add_skill_discovery_block()

  def setup_initial_context(self) -> None:
    """Add the system prompt (base behavior)."""
    if self._agent:
      self.add_message("system", self._agent.definition.system_prompt)

  def add_skill_discovery_block(self) -> None:
    """Add skill discovery user message if enabled and skills exist."""
    if not self._agent:
      return
    if len(self._agent.skills) > 0 and self._agent.config.skills.discovery:
      from yoker.skills import format_discovery_block

      skill_list = self._agent.skills.skills
      self.add_message("user", format_discovery_block(skill_list))
      logger.info("skill_discovery_added", skill_count=len(skill_list))

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
    self._messages.append(message)

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context."""
    self._messages.append(
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
    self._messages.append(assistant_msg)

  def get_context(self) -> list[dict[str, Any]]:
    """Get the full context for backend submission.

    Returns:
      List of message dictionaries in Ollama format.
    """
    return list(self._messages)

  def get_messages(self) -> list[dict[str, Any]]:
    """Get all recorded messages (excludes tool results).

    Returns:
      List of message dictionaries.
    """
    return [item for item in self._messages if item.get("role") != "tool"]

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

  def clear(self) -> None:
    """Clear in-memory context (does not delete persisted state)."""
    self._messages.clear()

  def save(self) -> None:
    """Persist context to storage. No-op in the base implementation."""

  def load(self) -> bool:
    """Load context from storage.

    Returns:
      False — the base implementation has no storage.
    """
    return False

  def delete(self) -> None:
    """Delete stored context from disk.

    Raises:
      NotImplementedError: The base implementation has no storage.
    """
    raise NotImplementedError("delete() not supported by this context manager")

  def get_statistics(self) -> ContextStatistics:
    """Get statistics about context usage."""
    message_count = sum(1 for item in self._messages if item.get("role") != "tool")
    turn_count = sum(1 for item in self._messages if item.get("role") == "user")

    return ContextStatistics(
      message_count=message_count,
      turn_count=turn_count,
      tool_call_count=0,
    )

  def close(self) -> None:
    """Release resources and flush any pending writes. No-op in the base."""

  def get_session_id(self) -> str:
    """Get the unique session identifier.

    Returns:
      "in-memory" for the base implementation.
    """
    return "in-memory"


__all__ = ["BaseContextManager"]
