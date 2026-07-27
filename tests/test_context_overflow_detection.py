"""Tests for context overflow detection (IP-12).

Verifies the hybrid token estimator and the ``_manage_context_overflow``
orchestration: under-cap is a no-op, over-cap runs the framework-default
truncation and emits a ``ContextOverflowEvent``, and thinking blocks are
stripped from non-supporting backends always-on (no config flag).
"""

from typing import Any
from unittest.mock import MagicMock

from yoker.context import BaseContextManager
from yoker.core._processing import (
  _estimate_tokens,
  _manage_context_overflow,
  _strip_thinking_blocks,
)
from yoker.events import ContextOverflowEvent, EventCallback, EventType


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
  m: dict[str, Any] = {"role": role, "content": content}
  m.update(extra)
  return m


class TestEstimateTokens:
  """Hybrid token estimation: UsageStats.input_tokens primary, char/4 fallback."""

  def test_uses_last_input_tokens_when_available(self) -> None:
    """When last_input_tokens is set, it is returned verbatim."""
    assert _estimate_tokens([_msg("user", "hi")], last_input_tokens=1234) == 1234

  def test_falls_back_to_char_div_4_when_no_usage(self) -> None:
    """With no usage signal, estimate is total content chars // 4."""
    msgs = [
      _msg("system", "abcd"),  # 4 chars -> 1
      _msg("user", "efgh"),  # 4 chars -> 1
    ]
    assert _estimate_tokens(msgs, last_input_tokens=None) == 2

  def test_zero_input_tokens_falls_back_to_heuristic(self) -> None:
    """A zero last_input_tokens is treated as no signal."""
    msgs = [_msg("user", "abcd")]
    assert _estimate_tokens(msgs, last_input_tokens=0) == 1

  def test_includes_thinking_and_tool_calls_in_heuristic(self) -> None:
    """The fallback sums content + thinking + tool_calls JSON lengths."""
    msgs = [
      {
        "role": "assistant",
        "content": "abcd",  # 4
        "thinking": "efgh",  # 4
        "tool_calls": [{"id": "call_1", "name": "read"}],  # JSON length > 0
      },
    ]
    estimate = _estimate_tokens(msgs, last_input_tokens=None)
    # (4 + 4 + len(json)) // 4 — at least 2 from content+thinking.
    assert estimate >= 2


class TestStripThinkingBlocks:
  """Thinking-block stripping is the always-on fallback for non-supporting backends."""

  def test_drops_thinking_key_from_each_message(self) -> None:
    """The thinking key is removed from every message that has one."""
    msgs = [
      {"role": "assistant", "content": "a", "thinking": "secret"},
      {"role": "user", "content": "b"},
    ]
    stripped = _strip_thinking_blocks(msgs)
    assert all("thinking" not in m for m in stripped)
    assert stripped[0]["content"] == "a"

  def test_does_not_mutate_caller_list(self) -> None:
    """The caller's list and dicts are not mutated."""
    original = {"role": "assistant", "content": "a", "thinking": "secret"}
    msgs = [original]
    _strip_thinking_blocks(msgs)
    assert original["thinking"] == "secret"

  def test_returns_list_of_same_length(self) -> None:
    """Stripping preserves message count and order."""
    msgs = [
      {"role": "user", "content": "1"},
      {"role": "assistant", "content": "2", "thinking": "t"},
      {"role": "user", "content": "3"},
    ]
    stripped = _strip_thinking_blocks(msgs)
    assert len(stripped) == 3
    assert [m["content"] for m in stripped] == ["1", "2", "3"]


def _make_agent(
  messages: list[dict[str, Any]],
  *,
  max_tokens: int,
  supports_context_management: bool = False,
) -> MagicMock:
  """Build a minimal mock agent for _manage_context_overflow."""
  cm = BaseContextManager()
  cm._messages = list(messages)

  backend = MagicMock()
  backend.supports_context_management = supports_context_management

  config = MagicMock()
  config.context.max_tokens = max_tokens
  config.context.overflow_keep_first_user = True

  agent = MagicMock()
  agent.context = cm
  agent._backend = backend
  agent.config = config
  agent._event_handlers = []
  return agent


class TestManageContextOverflow:
  """_manage_context_overflow: under-cap no-op, over-cap truncates + emits."""

  def test_under_cap_does_not_truncate(self) -> None:
    """When the estimate is under the cap, no messages are dropped."""
    agent = _make_agent(
      [_msg("system", "sys"), _msg("user", "hi")],
      max_tokens=10_000,
    )

    async def call() -> None:
      result = await _manage_context_overflow(agent, None, None)
      # Returns last_input_tokens (unchanged).
      assert result is None
      # No messages dropped.
      assert len(agent.context.get_context()) == 2

    import asyncio

    asyncio.run(call())

  def test_over_cap_truncates_and_emits_event(self) -> None:
    """Over the cap, the framework default drops messages and emits the event."""
    # max_tokens=1 forces overflow on any non-empty context.
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "first turn"),
        _msg("assistant", "resp1"),
        _msg("user", "second turn"),
        _msg("assistant", "resp2"),
      ],
      max_tokens=1,
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None, None))

    # At least one ContextOverflowEvent was emitted.
    overflow_events = [e for e in events if isinstance(e, ContextOverflowEvent)]
    assert len(overflow_events) >= 1
    event = overflow_events[0]
    assert event.type == EventType.CONTEXT_OVERFLOW
    assert event.max_tokens == 1
    assert event.estimated_tokens > 1
    assert event.dropped_count > 0
    # System messages survive (protected set).
    roles = [m["role"] for m in agent.context.get_context()]
    assert "system" in roles

  def test_thinking_blocks_stripped_for_non_supporting_backend(self) -> None:
    """Non-supporting backend: thinking blocks stripped even when under cap."""
    agent = _make_agent(
      [
        _msg("system", "sys"),
        {"role": "assistant", "content": "resp", "thinking": "secret"},
      ],
      max_tokens=10_000,
      supports_context_management=False,
    )
    import asyncio

    asyncio.run(_manage_context_overflow(agent, None, None))
    assert all("thinking" not in m for m in agent.context.get_context())

  def test_thinking_blocks_preserved_for_supporting_backend(self) -> None:
    """Supporting backend: thinking blocks stay (provider clears them)."""
    agent = _make_agent(
      [
        _msg("system", "sys"),
        {"role": "assistant", "content": "resp", "thinking": "secret"},
      ],
      max_tokens=10_000,
      supports_context_management=True,
    )
    import asyncio

    asyncio.run(_manage_context_overflow(agent, None, None))
    msgs = agent.context.get_context()
    assert any(m.get("thinking") == "secret" for m in msgs)

  def test_stale_last_input_tokens_does_not_evict_all_droppable(self) -> None:
    """Regression: the truncation loop must recalculate the estimate on
    the current (truncated) message list rather than reusing the stale
    last-turn ``last_input_tokens``. Otherwise the loop evicts ALL
    droppable messages instead of just enough to fit under the cap.
    """
    # last_input_tokens from the previous turn is far over the cap.
    stale_last_input_tokens = 5000
    # max_tokens=8; char/4 heuristic on the full list is 13, so only some
    # of the droppable assistants need to be evicted to reach 7 (<= 8).
    agent = _make_agent(
      [
        _msg("system", "sys"),  # 3 chars (protected)
        _msg("user", "hi"),  # 2 chars (protected first user turn)
        _msg("assistant", "abcdefgh"),  # 8 chars
        _msg("assistant", "abcdefgh"),
        _msg("assistant", "abcdefgh"),
        _msg("assistant", "abcdefgh"),
        _msg("assistant", "abcdefgh"),
        _msg("assistant", "abcdefgh"),
      ],
      max_tokens=8,
    )

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None, stale_last_input_tokens))

    final = agent.context.get_context()
    # The protected prefix (system + first user) survives.
    roles = [m["role"] for m in final]
    assert roles[0] == "system"
    assert "user" in roles
    # Critical assertion: NOT all droppable assistants were evicted.
    # Full list = 53 chars -> 13 tokens; dropping 3 assistants yields
    # 29 chars -> 7 tokens (<= 8), so 3 assistants survive.
    assistant_count = sum(1 for m in final if m["role"] == "assistant")
    assert assistant_count == 3, f"expected 3 assistants to survive, got {assistant_count}"
