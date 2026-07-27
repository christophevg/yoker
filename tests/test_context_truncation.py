"""Tests for context overflow truncation (IP-12).

Verifies ``truncate_oldest_non_system`` on BaseContextManager, Persisted,
and ContextManagerWrapper:
  - Protected set is preserved (system messages, skill-discovery user
    block, first real user turn).
  - Oldest non-setup messages dropped from the tail.
  - Tool-call-pair-aware (assistant tool_calls + tool results dropped
    together as an atomic unit).
  - Permanent removal from ``_messages``.
  - ``keep_first_user=False`` drops the first user turn too (except
    system messages and the scaffolding prefix).
  - Persisted: JSONL file rewritten after truncation.
  - Wrapper: delegates to wrapped.
"""

from typing import Any

import pytest

from yoker.context import (
  BaseContextManager,
  ContextManagerWrapper,
  Persisted,
)


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
  """Build a minimal message dict with optional extra fields."""
  m: dict[str, Any] = {"role": role, "content": content}
  m.update(extra)
  return m


def _tool_call_msg() -> dict[str, Any]:
  """Build an assistant message carrying one tool_call."""
  return {
    "role": "assistant",
    "content": "",
    "tool_calls": [{"id": "call_1", "name": "read", "arguments": {}}],
  }


def _tool_result_msg() -> dict[str, Any]:
  """Build a tool result message paired with _tool_call_msg()."""
  return {
    "role": "tool",
    "name": "read",
    "tool_id": "call_1",
    "content": "file contents",
    "success": True,
  }


class TestProtectedSetPreserved:
  """System messages, scaffolding prefix, and first real user turn survive."""

  def test_system_messages_always_protected(self) -> None:
    """All role=system messages stay after truncation."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys1"),
      _msg("system", "sys2"),
      _msg("user", "first real turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=10)
    # Only one droppable unit: "assistant resp2" (last). After that,
    # "user second turn" + "assistant resp1" become droppable, then
    # "user first real turn" is protected.
    assert dropped > 0
    roles = [m["role"] for m in cm._messages]
    assert roles.count("system") == 2
    assert _msg("system", "sys1") in cm._messages
    assert _msg("system", "sys2") in cm._messages

  def test_scaffolding_user_block_protected(self) -> None:
    """The contiguous user scaffolding prefix is preserved."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "skill discovery block"),
      _msg("user", "first real turn"),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.truncate_oldest_non_system(drop_count=10)
    contents = [m["content"] for m in cm._messages]
    assert "skill discovery block" in contents

  def test_first_real_user_turn_protected_when_keep_first_user_true(self) -> None:
    """keep_first_user=True protects the first real user turn."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "scaffold"),
      _msg("user", "first real turn"),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.truncate_oldest_non_system(keep_first_user=True, drop_count=10)
    contents = [m["content"] for m in cm._messages]
    assert "first real turn" in contents


class TestOldestDroppedFromTail:
  """Drops come from the oldest end of the droppable tail, in order.

  The protected prefix (system + scaffolding + first real user turn) is at
  the head. The droppable tail is everything after it. We drop the OLDEST
  droppable messages first — i.e. the ones closest to the protected prefix —
  so the most recent context survives.
  """

  def test_drop_one_atomic_unit_from_tail(self) -> None:
    """A single drop_count removes the oldest droppable atomic unit."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=1)
    assert dropped == 1
    contents = [m["content"] for m in cm._messages]
    # Oldest droppable is "resp1"; most recent "resp2" survives.
    assert "resp1" not in contents
    assert "resp2" in contents
    assert "second turn" in contents

  def test_drop_count_drops_multiple_units(self) -> None:
    """drop_count=2 removes the two oldest droppable atomic units."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=2)
    assert dropped == 2
    contents = [m["content"] for m in cm._messages]
    # Oldest two droppable: "resp1" and "second turn" (in order).
    assert "resp1" not in contents
    assert "second turn" not in contents
    assert "resp2" in contents


class TestToolCallPairAware:
  """Assistant tool_calls + trailing tool results are dropped together."""

  def test_tool_call_pair_dropped_atomically(self) -> None:
    """An assistant tool_calls message and its tool results drop together.

    The tool_call+tool_result pair is the OLDEST droppable unit (closest
    to the protected prefix), so it is the first unit dropped.
    """
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _tool_call_msg(),
      _tool_result_msg(),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=2)
    # First drop: tool_call + tool_result (2 msgs, one atomic unit).
    # Second drop: "resp1" (1 msg). Total = 3.
    assert dropped == 3
    roles = [m["role"] for m in cm._messages]
    assert "tool" not in roles
    # The assistant tool_calls message is gone.
    assert not any("tool_calls" in m for m in cm._messages)
    # "second turn" survives (most recent).
    contents = [m["content"] for m in cm._messages]
    assert "second turn" in contents

  def test_tool_call_pair_not_split_by_drop_count_one(self) -> None:
    """drop_count=1 drops the pair as a single unit, not just the assistant."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _tool_call_msg(),
      _tool_result_msg(),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=1)
    # The tool_call+tool_result pair is the oldest (and only) atomic unit:
    # dropped together as one unit, not just the assistant message.
    assert dropped == 2
    roles = [m["role"] for m in cm._messages]
    assert "tool" not in roles
    assert not any("tool_calls" in m for m in cm._messages)


class TestPermanentRemoval:
  """Dropped messages are permanently removed from _messages."""

  def test_dropped_messages_not_in_subsequent_get_context(self) -> None:
    """get_context() does not return dropped messages.

    drop_count=1 removes the OLDEST droppable unit ("resp1"); the most
    recent assistant response ("resp2") survives.
    """
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.truncate_oldest_non_system(drop_count=1)
    context = cm.get_context()
    contents = [m.get("content") for m in context]
    assert "resp1" not in contents
    assert "resp2" in contents

  def test_truncate_idempotent_when_no_droppable(self) -> None:
    """Truncating again after everything droppable is gone drops nothing."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
    ]
    dropped = cm.truncate_oldest_non_system(drop_count=5)
    assert dropped == 0
    assert len(cm._messages) == 2


class TestKeepFirstUserFalse:
  """keep_first_user=False drops the first real user turn too."""

  def test_first_user_turn_dropped_when_keep_first_user_false(self) -> None:
    """keep_first_user=False makes the first real user turn droppable."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "scaffold"),
      _msg("user", "first real turn"),
      _msg("assistant", "resp"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm.truncate_oldest_non_system(keep_first_user=False, drop_count=10)
    contents = [m["content"] for m in cm._messages]
    # System and scaffold are protected; first real turn is dropped.
    assert "sys" in contents
    assert "scaffold" in contents
    assert "first real turn" not in contents

  def test_system_messages_protected_even_when_keep_first_user_false(self) -> None:
    """System messages stay protected regardless of keep_first_user."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys1"),
      _msg("system", "sys2"),
      _msg("user", "first turn"),
      _msg("assistant", "resp"),
    ]
    cm.truncate_oldest_non_system(keep_first_user=False, drop_count=10)
    roles = [m["role"] for m in cm._messages]
    assert roles.count("system") == 2


class TestPersistedRewritesJsonl:
  """Persisted: JSONL file is rewritten after truncation."""

  def test_persisted_truncate_rewrites_jsonl(self, tmp_path: pytest.TempPathFactory) -> None:
    """Truncating a Persisted context rewrites the JSONL file."""
    cm = Persisted(
      BaseContextManager(),
      storage_path=tmp_path,
      session_id="test-trunc",
    )
    cm._wrapped._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    cm._persist_full_state(cm._wrapped.get_messages())

    dropped = cm.truncate_oldest_non_system(drop_count=1)
    assert dropped == 1

    # Reload from disk and verify the dropped message is gone. The oldest
    # droppable unit ("resp1") was dropped; "resp2" survives.
    reloaded = Persisted(
      BaseContextManager(),
      storage_path=tmp_path,
      session_id="test-trunc",
    )
    assert reloaded.load() is True
    contents = [m.get("content") for m in reloaded.get_context()]
    assert "resp1" not in contents
    assert "resp2" in contents


class TestWrapperDelegates:
  """ContextManagerWrapper delegates truncate to the wrapped manager."""

  def test_wrapper_delegates_truncate(self) -> None:
    """Wrapper.truncate_oldest_non_system forwards to wrapped."""
    inner = BaseContextManager()
    inner._messages = [
      _msg("system", "sys"),
      _msg("user", "first turn"),
      _msg("assistant", "resp1"),
      _msg("user", "second turn"),
      _msg("assistant", "resp2"),
    ]
    wrapper = ContextManagerWrapper(inner)
    dropped = wrapper.truncate_oldest_non_system(drop_count=1)
    assert dropped == 1
    contents = [m["content"] for m in inner._messages]
    # Oldest droppable ("resp1") is dropped; "resp2" survives.
    assert "resp1" not in contents
    assert "resp2" in contents

  def test_wrapper_replace_messages_delegates(self) -> None:
    """Wrapper.replace_messages forwards to wrapped."""
    inner = BaseContextManager()
    inner._messages = [_msg("system", "sys")]
    wrapper = ContextManagerWrapper(inner)
    wrapper.replace_messages([_msg("system", "new"), _msg("user", "u")])
    assert len(inner._messages) == 2
    assert inner._messages[0]["content"] == "new"


class TestReplaceMessages:
  """replace_messages atomically swaps the internal list."""

  def test_replace_messages_swaps_list(self) -> None:
    """replace_messages replaces the entire internal message list."""
    cm = BaseContextManager()
    cm._messages = [_msg("system", "old")]
    new_msgs = [_msg("system", "new"), _msg("user", "u")]
    cm.replace_messages(new_msgs)
    assert cm._messages == new_msgs

  def test_replace_messages_copies_caller_list(self) -> None:
    """replace_messages copies the caller's list (no shared reference)."""
    cm = BaseContextManager()
    new_msgs = [_msg("system", "new")]
    cm.replace_messages(new_msgs)
    new_msgs.append(_msg("user", "late"))
    assert len(cm._messages) == 1
