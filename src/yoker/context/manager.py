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
    content: str = "",
  ) -> None:
    """Add an assistant message with tool calls to the context.

    This must be called BEFORE add_tool_result() for each tool call.

    Args:
      tool_calls: List of tool call dictionaries with 'name' and 'arguments'.
      thinking: Optional thinking/reasoning content from the assistant.
      content: Optional assistant narration text produced alongside the
        tool calls (when the LLM emits both text and tool calls in one
        response). Stored so the LLM can see its own prior reasoning on
        subsequent iterations.
    """
    assistant_msg: dict[str, Any] = {
      "role": "assistant",
      "tool_calls": tool_calls,
      "content": content,
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

  def truncate_oldest_non_system(
    self,
    keep_first_user: bool = True,
    drop_count: int = 1,
  ) -> int:
    """Permanently drop the oldest non-setup messages from the tail.

    See ``ContextManager.truncate_oldest_non_system`` in the Protocol for
    the full contract. Works on a copy of ``_messages`` (per the security
    refinement: never mutate in place during iteration) and assigns the
    truncated list back atomically.

    Args:
      keep_first_user: Protect the first real user turn when True.
      drop_count: Number of atomic units to drop.

    Returns:
      The number of messages permanently removed.
    """
    if drop_count <= 0 or not self._messages:
      return 0

    protected_end = self._protected_prefix_end(keep_first_user)
    # Build atomic units from the droppable tail (indices >= protected_end).
    units = self._atomic_units(protected_end)
    if not units:
      return 0

    to_drop = min(drop_count, len(units))
    dropped_indices: set[int] = set()
    for _ in range(to_drop):
      if not units:
        break
      start, end = units.pop(0)
      dropped_indices.update(range(start, end + 1))

    if not dropped_indices:
      return 0

    # Work on a copy, then assign back atomically (no in-place mutation
    # during iteration).
    new_messages = [
      item for idx, item in enumerate(list(self._messages)) if idx not in dropped_indices
    ]
    dropped_count = len(self._messages) - len(new_messages)
    self._messages = new_messages
    return dropped_count

  def replace_messages(self, messages: list[dict[str, Any]]) -> None:
    """Replace the entire internal message list atomically.

    See ``ContextManager.replace_messages`` in the Protocol for the full
    contract. Used by the overflow hook (validated replacement list) and
    the thinking-block stripping fallback.
    """
    self._messages = list(messages)

  def _protected_prefix_end(self, keep_first_user: bool) -> int:
    """Return the exclusive end index of the protected prefix.

    The protected prefix is always a contiguous run at the head of
    ``_messages``:
      - all ``role=system`` messages (setup)
      - the contiguous ``role=user`` scaffolding prefix (user messages
        emitted by ``add_skill_discovery_block`` and any other user
        messages that appear before the first non-user/non-system
        message)
      - the first real user turn: the last user message in the
        contiguous user prefix (the one immediately followed by an
        assistant or tool message), when ``keep_first_user`` is True

    Once we leave the protected prefix (encounter an assistant or tool
    message after the user run, or hit a second user turn past the first
    real one when ``keep_first_user`` is True), the rest is droppable.

    The contiguous user prefix is a single block: all leading user
    messages. The last user in that block is the first real user turn;
    the earlier ones are the scaffolding prefix (skill discovery, etc.).
    """
    n = len(self._messages)
    i = 0
    # System messages: always protected.
    while i < n and self._messages[i].get("role") == "system":
      i += 1
    # Contiguous user prefix (scaffolding + first real user turn).
    user_run_start = i
    while i < n and self._messages[i].get("role") == "user":
      i += 1
    # ``user_run_start..i`` is the contiguous user block. The last user
    # message in this block (index ``i - 1``) is the first real user turn
    # — it is the user message immediately followed by a non-user message.
    # If the block runs to the end of the list (no assistant/tool after),
    # there is no "first real user turn" yet: every user message is
    # pending/current and stays protected.
    has_real_turn = i < n and self._messages[i].get("role") in ("assistant", "tool")
    if keep_first_user or not has_real_turn:
      # Protect the entire contiguous user block (scaffolding + first
      # real user turn, or all pending user messages when there is no
      # real turn yet).
      return i
    # keep_first_user=False with a real turn: protect the scaffolding
    # prefix only. Drop the first real user turn (the last user in the
    # block), protecting indices user_run_start..i-2.
    if i == user_run_start:
      return i
    return i - 1

  def _atomic_units(self, start: int) -> list[tuple[int, int]]:
    """Group droppable messages (indices >= start) into atomic units.

    An atomic unit is either:
      - a single message without ``tool_calls``, or
      - an assistant message with ``tool_calls`` followed by all its
        trailing contiguous ``role=tool`` result messages (dropped
        together so tool-call/tool-result pairing is never split).

    Returns:
      A list of (start_index, end_index) inclusive tuples, in order.
    """
    units: list[tuple[int, int]] = []
    i = start
    n = len(self._messages)
    while i < n:
      msg = self._messages[i]
      if msg.get("role") == "assistant" and "tool_calls" in msg:
        unit_start = i
        i += 1
        # Consume trailing tool result messages.
        while i < n and self._messages[i].get("role") == "tool":
          i += 1
        units.append((unit_start, i - 1))
      else:
        units.append((i, i))
        i += 1
    return units

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
