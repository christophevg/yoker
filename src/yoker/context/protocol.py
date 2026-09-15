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
    images: list[str] | None = None,
  ) -> None:
    """Add a tool execution result to the context.

    ``images`` holds image file paths (references, not base64) for the
    model to see; the ollama backend serializes them at submission time.
    """

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
    content: str = "",
  ) -> None:
    """Add an assistant message carrying tool_calls. Must precede add_tool_result."""

  # --- reads ---

  def get_context(self) -> list[dict[str, Any]]:
    """Full context for backend submission (includes tool results).

    Image refs on tool messages follow a send-once contract: refs are
    included only for tool messages after the most recent assistant
    message and dropped from older ones (described in text by the model
    instead). Stored messages are never mutated.
    """

  def get_messages(self) -> list[dict[str, Any]]:
    """All recorded messages (excludes tool results)."""

  def get_stored_messages(self) -> list[dict[str, Any]]:
    """All stored messages — the compaction TRUTH the projection views.

    Includes tool results and everything get_context() may hide or stub:
    persistence must save this, not the projection.
    """

  @property
  def strip_thinking_in_view(self) -> bool:
    """Whether the projection drops unflagged thinking (see get_context)."""
    return True

  @strip_thinking_in_view.setter
  def strip_thinking_in_view(self, value: bool) -> None:
    del value

  # --- context overflow management ---

  def truncate_oldest_non_system(
    self,
    protect_first_user: int = 1,
    protect_last_user: int = 1,
    protect_last_assistant: int = 1,
    protect_last_tool_calls: int = 1,
    drop_count: int = 1,
    run: str | None = None,
  ) -> int:
    """Flag the oldest non-protected messages as dropped — no physical removal.

    Compaction treats stored messages as TRUTH: selected messages are
    marked with ``pruned.kind == "dropped"`` metadata and excluded from
    the submitted view (get_context), while the store and the persisted
    history keep everything.

    The protected set is never flagged:
      - all ``role=system`` messages
      - the contiguous ``role=user`` scaffolding prefix emitted by
        :meth:`add_skill_discovery_block` (and any other user messages
        that appear before the first real user turn)
      - the first ``protect_first_user`` real user messages after the
        scaffolding prefix
      - the last ``protect_last_user`` user messages in the whole store
      - the last ``protect_last_assistant`` plain assistant messages
        (``role=assistant`` without ``tool_calls``)
      - the last ``protect_last_tool_calls`` tool-call units — an
        assistant ``tool_calls`` frame plus all its trailing
        ``role=tool`` result messages, protected together

    Tool-call pairs are flagged atomically: an assistant message carrying
    ``tool_calls`` is never split from its trailing ``role=tool`` result
    messages — they are flagged together as a single unit. Already-flagged
    units are skipped without consuming ``drop_count``.

    Args:
      protect_first_user: Number of first real user messages (after the
        scaffolding prefix) to protect.
      protect_last_user: Number of last user messages to protect.
      protect_last_assistant: Number of last plain assistant messages to
        protect.
      protect_last_tool_calls: Number of last tool-call units to protect
        (frame + results together).
      drop_count: Number of atomic units (tool-call-pair-aware) to flag.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of messages newly flagged as dropped.
    """

  def protected_view(
    self,
    protect_first_user: int = 1,
    protect_last_user: int = 1,
    protect_last_assistant: int = 1,
    protect_last_tool_calls: int = 1,
  ) -> list[dict[str, Any]]:
    """The cutoff-protected subset rendered exactly as get_context renders.

    Same protected set as :meth:`protected_context` (framework
    scaffolding + the four protection windows, store order), but passed
    through the shared projection (stub rendering, thinking strips,
    flag removal, image contract) — the protection floor the cutoff
    stage can never go below, in backend-submission shape.
    """

  def replace_messages(self, messages: list[dict[str, Any]]) -> None:
    """Replace the entire internal message list atomically.

    Used by the context-overflow machinery:
      - the ``on_context_overflow`` hook may return a validated
        replacement message list, which is applied via this method;
      - the thinking-block stripping fallback (for backends that do not
        support a provider-side ``context_management`` directive) replaces
        the message list with a stripped copy so thinking blocks from
        prior turns do not accumulate. (Superseded: stripping now happens
        at projection level in get_context; replace_messages remains for
        the overflow hook.)

    Implementations that persist (e.g. :class:`Persisted`) must rewrite
    their storage after replacing the in-memory list.

    Args:
      messages: The new message list (owned by the context manager after
        the call; callers should not retain references to the same list).
    """

  def prune_tool_results(self, min_age_turns: int, min_chars: int, run: str | None = None) -> int:
    """Flag old, large tool results as stubs — no physical removal.

    Framework-default compaction pipeline stage. Selection: ``role=tool``
    messages whose body exceeds ``min_chars`` chars and whose age is at
    least ``min_age_turns`` completed turns (position-derived, never
    wall-clock). User/assistant/system and already-flagged messages are
    never touched. Tool-call pairing stays intact: the flagged result
    keeps role/name/tool_id and the projection renders a deterministic
    stub.

    Args:
      min_age_turns: Minimum completed turns after the result to flag it.
      min_chars: Minimum body length (chars) for a result to be stubbed.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of tool results newly flagged as stubs.
    """

  def force_stub_tool_results(self, min_chars: int, run: str | None = None) -> int:
    """Flag every large tool result as a stub, regardless of age — no removal.

    Framework-default compaction pipeline stage: the age-blind, last
    content-preserving pass before the destructive cutoff — stubs EVERY
    ``role=tool`` result whose body exceeds ``min_chars`` (already
    flagged, non-tool and short-body messages are never touched).

    Args:
      min_chars: Minimum body length (chars) for a result to be stubbed.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of tool results newly flagged as stubs.
    """

  def prune_thinking(self, min_age_turns: int, run: str | None = None) -> int:
    """Flag old ``thinking`` payloads as pruned — no physical removal.

    Framework-default compaction pipeline stage. Flags messages whose
    ``thinking`` payload is at least ``min_age_turns`` completed turns old
    (position-derived age) with ``pruned.kind == "thinking"``; the
    projection strips flagged thinking for every backend while the message
    itself stays in the view.

    Args:
      min_age_turns: Minimum completed turns after the message to flag it.
      run: Optional compaction run id stored in the flag metadata, so
        per-run reporting can count THIS run's flags.

    Returns:
      The number of messages newly flagged.
    """

  # --- compaction run reporting ---

  def record_compaction(self, run: dict[str, Any]) -> None:
    """Record a compaction run report for later persistence (chunk C)."""

  @property
  def compaction_runs(self) -> list[dict[str, Any]]:
    """Copies of the recorded compaction run reports, oldest first."""

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
