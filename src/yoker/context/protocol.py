"""ContextManager Protocol definition.

Defines the @runtime_checkable Protocol that all context managers
(BaseContextManager, SimpleContextManager, ContextManagerWrapper, Persisted)
satisfy structurally. The Protocol captures the full surface used by the
Agent and the processing loop.

The list surface (``__getitem__``, ``__len__``, ``__iter__``, ``append``,
``data``) is intentionally absent — callers use ``get_messages()`` /
``get_context()`` / the adder methods.
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from yoker.context.interface import ContextStatistics

if TYPE_CHECKING:
  from yoker.core import Agent


@runtime_checkable
class ContextManager(Protocol):
  """Pluggable context manager for conversation history.

  Implementations:
  - :class:`yoker.context.manager.BaseContextManager` — in-memory base.
  - :class:`yoker.context.basic.SimpleContextManager` — adds env reminder.
  - :class:`yoker.context.wrapper.ContextManagerWrapper` — pure proxy.
  - :class:`yoker.context.persisted.Persisted` — JSONL persistence wrapper.
  """

  # --- agent reference ---

  @property
  def agent(self) -> "Agent | None": ...

  @agent.setter
  def agent(self, new_agent: "Agent") -> None: ...

  # --- context setup ---

  def setup_initial_context(self) -> None:
    """Add the initial system prompt / context messages."""

  def add_skill_discovery_block(self) -> None:
    """Add the skill-discovery user message, if enabled."""

  # --- message mutation ---

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    thinking: str | None = None,
  ) -> None:
    """Add a message (user / assistant / system) to the context."""

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    """Add a tool execution result to the context."""

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
  ) -> None:
    """Add an assistant message carrying tool_calls. Must precede add_tool_result."""

  # --- reads ---

  def get_context(self) -> list[dict[str, Any]]:
    """Full context for backend submission (includes tool results)."""

  def get_messages(self) -> list[dict[str, Any]]:
    """All recorded messages (excludes tool results)."""

  # --- context overflow management ---

  def truncate_oldest_non_system(
    self,
    keep_first_user: bool = True,
    drop_count: int = 1,
  ) -> int:
    """Permanently drop the oldest non-setup messages from the tail.

    The protected set is never dropped:
      - all ``role=system`` messages
      - the contiguous ``role=user`` scaffolding prefix emitted by
        :meth:`add_skill_discovery_block` (and any other user messages
        that appear before the first real user turn)
      - the first real user turn (the first ``role=user`` message after
        the scaffolding prefix) when ``keep_first_user`` is True

    Tool-call pairs are dropped atomically: an assistant message carrying
    ``tool_calls`` is never split from its trailing ``role=tool`` result
    messages — they are dropped together as a single unit.

    Args:
      keep_first_user: When True, protect the first real user turn in
        addition to system messages and the scaffolding prefix. When
        False, the first user turn is also eligible for dropping (system
        messages remain protected).
      drop_count: Number of atomic units (tool-call-pair-aware) to drop.

    Returns:
      The number of messages permanently removed from ``_messages``.
    """

  def replace_messages(self, messages: list[dict[str, Any]]) -> None:
    """Replace the entire internal message list atomically.

    Used by the context-overflow machinery:
      - the ``on_context_overflow`` hook may return a validated
        replacement message list, which is applied via this method;
      - the thinking-block stripping fallback (for backends that do not
        support a provider-side ``context_management`` directive) replaces
        the message list with a stripped copy so thinking blocks from
        prior turns do not accumulate.

    Implementations that persist (e.g. :class:`Persisted`) must rewrite
    their storage after replacing the in-memory list.

    Args:
      messages: The new message list (owned by the context manager after
        the call; callers should not retain references to the same list).
    """

  # --- turn lifecycle ---

  def start_turn(self, user_message: str) -> None:
    """Start a new conversation turn."""

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    """End the current conversation turn."""

  # --- storage lifecycle ---

  def clear(self) -> None:
    """Clear in-memory context (does not delete persisted state)."""

  def save(self) -> None:
    """Persist context to storage. No-op in base."""

  def load(self) -> bool:
    """Load context from storage. Return True if loaded, False if none."""

  def delete(self) -> None:
    """Delete stored context from disk."""

  def close(self) -> None:
    """Release resources and flush pending writes."""

  # --- introspection ---

  def get_statistics(self) -> ContextStatistics:
    """Return context-usage statistics."""

  def get_session_id(self) -> str:
    """Return the unique session identifier."""


__all__ = ["ContextManager"]
