"""ContextManagerWrapper — pure proxy implementing the ContextManager Protocol.

A no-op baseclass for all wrappers. Holds a wrapped ContextManager and
forwards every Protocol method to it. Subclasses (Persisted) override
mutating methods to add side effects after delegating.
"""

from typing import TYPE_CHECKING, Any

from yoker.context.interface import ContextStatistics
from yoker.context.protocol import ContextManager

if TYPE_CHECKING:
  from yoker.core import Agent


class ContextManagerWrapper:
  """Pure proxy implementing the ContextManager Protocol.

  Does not inherit from BaseContextManager or UserList. Every Protocol
  method forwards to ``self._wrapped``. Subclasses override mutating
  methods to add side effects (e.g. JSONL persistence in Persisted).
  """

  def __init__(self, wrapped: ContextManager) -> None:
    """Initialize the wrapper.

    Args:
      wrapped: The wrapped ContextManager instance.
    """
    self._wrapped: ContextManager = wrapped

  # --- agent reference ---

  @property
  def agent(self) -> "Agent | None":
    return self._wrapped.agent

  @agent.setter
  def agent(self, new_agent: "Agent") -> None:
    self._wrapped.agent = new_agent

  # --- context setup ---

  def setup_initial_context(self) -> None:
    self._wrapped.setup_initial_context()

  def add_skill_discovery_block(self) -> None:
    self._wrapped.add_skill_discovery_block()

  # --- message mutation ---

  def add_message(
    self,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    thinking: str | None = None,
  ) -> None:
    self._wrapped.add_message(role, content, metadata=metadata, thinking=thinking)

  def add_tool_result(
    self,
    tool_name: str,
    tool_id: str,
    result: str,
    success: bool = True,
  ) -> None:
    self._wrapped.add_tool_result(tool_name, tool_id, result, success=success)

  def add_tool_calls(
    self,
    tool_calls: list[dict[str, Any]],
    thinking: str | None = None,
    content: str = "",
  ) -> None:
    self._wrapped.add_tool_calls(tool_calls, thinking=thinking, content=content)

  # --- reads ---

  def get_context(self) -> list[dict[str, Any]]:
    return self._wrapped.get_context()

  def get_messages(self) -> list[dict[str, Any]]:
    return self._wrapped.get_messages()

  def get_stored_messages(self) -> list[dict[str, Any]]:
    return self._wrapped.get_stored_messages()

  @property
  def strip_thinking_in_view(self) -> bool:
    """Forward the projection thinking-strip switch to the wrapped manager."""
    return getattr(self._wrapped, "strip_thinking_in_view", True)

  @strip_thinking_in_view.setter
  def strip_thinking_in_view(self, value: bool) -> None:
    self._wrapped.strip_thinking_in_view = value

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
    return self._wrapped.truncate_oldest_non_system(
      protect_first_user=protect_first_user,
      protect_last_user=protect_last_user,
      protect_last_assistant=protect_last_assistant,
      protect_last_tool_calls=protect_last_tool_calls,
      drop_count=drop_count,
      run=run,
    )

  def protected_view(
    self,
    protect_first_user: int = 1,
    protect_last_user: int = 1,
    protect_last_assistant: int = 1,
    protect_last_tool_calls: int = 1,
  ) -> list[dict[str, Any]]:
    return self._wrapped.protected_view(
      protect_first_user=protect_first_user,
      protect_last_user=protect_last_user,
      protect_last_assistant=protect_last_assistant,
      protect_last_tool_calls=protect_last_tool_calls,
    )

  def replace_messages(self, messages: list[dict[str, Any]]) -> None:
    self._wrapped.replace_messages(messages)

  # --- context overflow pipeline stages ---

  def prune_tool_results(self, min_age_turns: int, min_chars: int, run: str | None = None) -> int:
    return self._wrapped.prune_tool_results(min_age_turns, min_chars, run=run)

  def force_stub_tool_results(self, min_chars: int, run: str | None = None) -> int:
    return self._wrapped.force_stub_tool_results(min_chars, run=run)

  def prune_thinking(self, min_age_turns: int, run: str | None = None) -> int:
    return self._wrapped.prune_thinking(min_age_turns, run=run)

  # --- compaction run reporting ---

  def record_compaction(self, run: dict[str, Any]) -> None:
    self._wrapped.record_compaction(run)

  @property
  def compaction_runs(self) -> list[dict[str, Any]]:
    return self._wrapped.compaction_runs

  # --- turn lifecycle ---

  def start_turn(self, user_message: str) -> None:
    self._wrapped.start_turn(user_message)

  def end_turn(self, assistant_message: str, thinking: str | None = None) -> None:
    self._wrapped.end_turn(assistant_message, thinking=thinking)

  # --- storage lifecycle ---

  def clear(self) -> None:
    self._wrapped.clear()

  def save(self) -> None:
    self._wrapped.save()

  def load(self) -> bool:
    return self._wrapped.load()

  def delete(self) -> None:
    self._wrapped.delete()

  def close(self) -> None:
    self._wrapped.close()

  # --- introspection ---

  def get_statistics(self) -> ContextStatistics:
    return self._wrapped.get_statistics()

  def get_session_id(self) -> str:
    return self._wrapped.get_session_id()


__all__ = ["ContextManagerWrapper"]
