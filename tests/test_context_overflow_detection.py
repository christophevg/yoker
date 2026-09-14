"""Tests for context overflow detection (IP-12).

Verifies the hybrid token estimator and the ``_manage_context_overflow``
orchestration: under-cap is a no-op, over-cap runs the framework-default
truncation and emits a ``ContextOverflowEvent``, and thinking blocks are
stripped from non-supporting backends always-on (no config flag).
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.context import BaseContextManager
from yoker.core._processing import (
  _calibrated_estimate,
  _capture_calibration,
  _estimate_tokens,
  _first_remaining_summary,
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
  compact_ratio: float = 1.0,
) -> MagicMock:
  """Build a minimal mock agent for _manage_context_overflow.

  ``compact_ratio`` defaults to 1.0 so trim-mechanics tests keep pinning
  the cap-exact behavior; hysteresis tests pass 0.5 explicitly.
  """
  cm = BaseContextManager()
  cm._messages = list(messages)

  backend = MagicMock()
  backend.supports_context_management = supports_context_management

  config = MagicMock()
  config.context.max_tokens = max_tokens
  config.context.overflow_keep_first_user = True
  config.context.compact_ratio = compact_ratio

  agent = MagicMock()
  agent.context = cm
  agent._backend = backend
  agent.config = config
  agent._event_handlers = []
  # Calibration state — set explicitly (MagicMock auto-attributes would be
  # truthy Mocks and break _calibrated_estimate).
  agent._context_fixed_tokens = None
  agent._context_ratio = 1.0
  agent._context_char4_at_capture = None
  agent._context_last_input_tokens = None
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
      await _manage_context_overflow(agent, None)
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

    asyncio.run(_manage_context_overflow(agent, None))

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

    asyncio.run(_manage_context_overflow(agent, None))
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

    asyncio.run(_manage_context_overflow(agent, None))
    msgs = agent.context.get_context()
    assert any(m.get("thinking") == "secret" for m in msgs)

  def test_calibrated_dropping_drops_only_needed_units(self) -> None:
    """Calibrated overage drops only enough units to cover it.

    Regression for the "Dropped 0" bug: when the calibrated count (which
    includes system prompt + tool schemas overhead) is over the cap while
    the char/4 content estimate alone is under it, the loop must still
    drop messages — charged against the calibrated count, not re-derived
    from the heuristic.
    """
    # max_tokens=20; calibrated estimate = 13 char4 content + 15 fixed
    # = 28 -> overage 8. Each 8-char assistant is worth 2 content tokens
    # (8 // 4), so 4 units cover the overage and the newest 2 assistants
    # survive. The char/4 estimate of the full list is 13 (<= 20) — the
    # old code would have dropped 0.
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "hi"),
        _msg("assistant", "one1one1"),
        _msg("assistant", "two2two2"),
        _msg("assistant", "three333"),
        _msg("assistant", "four4444"),
        _msg("assistant", "five5555"),
        _msg("assistant", "six6six6"),
      ],
      max_tokens=20,
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    # Seed calibration: fixed=15, ratio=1.0 — the calibrated estimate of
    # the full list (13 content + 15 fixed = 28) is over the 20 cap, so
    # the loop fires. Charging at ratio 1.0 drops char/4-equivalents.
    agent._context_fixed_tokens = 15
    agent._context_ratio = 1.0

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    final = agent.context.get_context()
    roles = [m["role"] for m in final]
    assert roles[0] == "system"
    assert "user" in roles
    # Oldest units dropped first; enough units dropped to cover the
    # calibrated overage (28 > 20), event reports the total.
    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count >= 1
    assert event.estimated_tokens == 28
    assert event.max_tokens == 20
    assert agent._context_ratio == 1.0  # unchanged by the loop
    # The newest two assistants survive (8 tokens of overage covered by
    # 4 dropped units charged at 2 each).
    assistants = [m["content"] for m in final if m["role"] == "assistant"]
    assert assistants == ["five5555", "six6six6"]

  def test_calibrated_massive_overage_drops_all_droppable(self) -> None:
    """Calibrated count far over the cap: every droppable unit is dropped.

    The protected prefix (system + first user turn) survives. A count far
    over the cap genuinely requires evicting all droppable history — the
    cap is enforced.
    """
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "hi"),
        *[_msg("assistant", "abcdefgh") for _ in range(6)],
      ],
      max_tokens=8,
    )
    agent._context_fixed_tokens = 5000
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    final = agent.context.get_context()
    roles = [m["role"] for m in final]
    assert roles[0] == "system"
    assert "user" in roles
    assistant_count = sum(1 for m in final if m["role"] == "assistant")
    assert assistant_count == 0
    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count == 6
    # Calibrated estimate: 53 content chars // 4 = 13, + fixed 5000.
    assert event.estimated_tokens == 5013

  def test_calibrated_ratio_charges_dense_content(self) -> None:
    """Dense content (high learned ratio) needs fewer dropped messages.

    ratio=4.0: each dropped unit is charged 4× its char/4 size, so the
    loop stops earlier than at ratio 1.0 for the same fixed overhead.
    """
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "hi"),
        *[_msg("assistant", "abcdefgh") for _ in range(6)],
      ],
      max_tokens=8,
    )
    agent._context_fixed_tokens = 50
    agent._context_ratio = 4.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    # Estimate: content 53 chars (sys 3 + hi 2 + 6×8) // 4 = 13;
    # 50 + 4.0*13 = 102. Each dropped unit charged 4*2 = 8 → overage 94
    # → 12 units would be needed but only 6 droppable — all 6 dropped,
    # loop stops dry.
    assert event.dropped_count == 6
    assert event.estimated_tokens == 102

  def test_all_protected_emits_zero_drop_event(self) -> None:
    """Nothing droppable (system + protected first user only): the event
    still fires with dropped_count 0 — a real saturation signal, not the
    estimator-mismatch artifact it used to be.
    """
    agent = _make_agent(
      [_msg("system", "sys"), _msg("user", "hello")],
      max_tokens=1,
    )
    # Seed calibration: fixed=1, ratio=1.0 → estimate = 2 char4 + 1 fixed.
    agent._context_fixed_tokens = 1
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count == 0
    # Calibrated estimate: "hello"=5, "sys"=3 → 8 chars // 4 = 2, + fixed 1.
    assert event.estimated_tokens == 3
    assert len(agent.context.get_context()) == 2

  def test_first_remaining_reports_history_start(self) -> None:
    """The event's first_remaining names the first non-protected message."""
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "first turn"),
        _msg("assistant", "resp1"),
        _msg("user", "second turn"),
        _msg("assistant", "resp2"),
      ],
      max_tokens=8,
    )
    # Seed calibration: char4 of the full list is 34//4 = 8; fixed=1 →
    # estimate 9 > cap 8 → overage 1. Dropping resp1 (charge 1) covers
    # it exactly; "second turn" merges into the contiguous protected
    # user block, and "resp2" survives as retained history.
    agent._context_fixed_tokens = 1
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count == 1
    assert event.estimated_tokens == 9
    # Protected prefix: system + the contiguous user block ("first
    # turn", "second turn"). History starts at the retained "resp2".
    assert event.first_remaining == "assistant: resp2"

  def test_first_remaining_none_when_only_protected_remains(self) -> None:
    """Only the protected prefix remains → first_remaining is None."""
    agent = _make_agent(
      [_msg("system", "sys"), _msg("user", "only turn")],
      max_tokens=1,
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count == 0
    assert event.first_remaining is None

  def test_first_remaining_tool_call_summary(self) -> None:
    """An assistant message with tool calls summarizes as role → tools."""

    msgs = [
      _msg("system", "sys"),
      _msg("user", "first"),
      {
        "role": "assistant",
        "content": "Let me check",
        "tool_calls": [
          {"function": {"name": "read"}},
          {"function": {"name": "read"}},
          {"function": {"name": "make"}},
        ],
      },
    ]
    summary = _first_remaining_summary(msgs)
    assert summary == "assistant → tools: read ×2, make | Let me check"


class TestCompactRatioHysteresis:
  """Trim-target hysteresis: the loop stops at max_tokens * compact_ratio."""

  def test_ratio_trims_deeper_than_cap(self) -> None:
    """ratio 0.5 on cap 30 trims to ≈15, dropping far more than needed."""
    # char4 of the full list: "sys"(3) + "hi"(2) + 10×8 = 85 // 4 = 21.
    # Seed fixed=15 → calibrated estimate 15 + 21 = 36 > cap 30 (trigger).
    # Target = int(30 * 0.5) = 15 → overage 21; each 8-char assistant
    # charges 2, so after 10 drops overage is 1 and the loop runs dry.
    # A cap-exact trim would need only 3 drops (overage 6) — hysteresis
    # drops 10.
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "hi"),
        *[_msg("assistant", "abcdefgh") for _ in range(10)],
      ],
      max_tokens=30,
      compact_ratio=0.5,
    )
    agent._context_fixed_tokens = 15
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.max_tokens == 30
    assert event.estimated_tokens == 36
    assert event.target_tokens == 15
    assert event.dropped_count == 10  # deeper than the 3 a cap-trim needs
    # Ratio 1.0 would have kept 7 assistants; the target leaves none.
    assistants = [m for m in agent.context.get_context() if m["role"] == "assistant"]
    assert assistants == []

  def test_ratio_one_reproduces_cap_trim_exactly(self) -> None:
    """compact_ratio 1.0 keeps the trim-to-cap behavior byte-for-byte."""
    # Same setup as above but ratio 1.0: overage = 36 - 30 = 6 → 3 drops,
    # newest 7 assistants survive.
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "hi"),
        *[_msg("assistant", "abcdefgh") for _ in range(10)],
      ],
      max_tokens=30,
      compact_ratio=1.0,
    )
    agent._context_fixed_tokens = 15
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.max_tokens == 30
    assert event.estimated_tokens == 36
    assert event.target_tokens == 30
    assert event.dropped_count == 3
    final = agent.context.get_context()
    assert len(final) == 9  # system + user + 7 assistants (12 - 3)

  def test_missing_compact_ratio_defends_to_one(self) -> None:
    """A config without compact_ratio behaves like ratio 1.0."""
    # Same scenario as test_ratio_trims_deeper_than_cap (which drops all
    # 10 at ratio 0.5); the missing attribute must fall back to 1.0 and
    # stop at the cap after 3 drops.
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "hi"),
        *[_msg("assistant", "abcdefgh") for _ in range(10)],
      ],
      max_tokens=30,
    )
    del agent.config.context.compact_ratio  # MagicMock: attribute gone
    agent._context_fixed_tokens = 15
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.target_tokens == 30
    assert event.dropped_count == 3

  def test_event_carries_target_tokens(self) -> None:
    """The emitted event reports the effective trim target."""
    # Nothing droppable (protected prefix only): the event still fires.
    # Seed calibration so the estimate is over the cap: "sys"=3 + "hi"=2
    # = 5 chars // 4 = 1, + fixed 2 → 3 > cap 1.
    agent = _make_agent(
      [_msg("system", "sys"), _msg("user", "hi")],
      max_tokens=1,
      compact_ratio=0.5,
    )
    agent._context_fixed_tokens = 2
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.target_tokens == 0  # int(1 * 0.5)

  def test_first_remaining_correct_after_deeper_trim(self) -> None:
    """A deep target trim still reports the true retained-history start."""
    # char4: "sys"(3) + "first turn"(10) + "second turn"(11) + 3×8=24
    # = 48 // 4 = 12; fixed=1 → estimate 13 > cap 10. Target = 5 →
    # overage 8: each 8-char assistant charges 2, so all 3 assistants
    # are dropped (overage 2 remains — nothing droppable left);
    # "second turn" merges into the protected user block, so nothing but
    # the prefix remains.
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "first turn"),
        _msg("user", "second turn"),
        _msg("assistant", "resp1resp"),
        _msg("assistant", "resp2resp"),
        _msg("assistant", "resp3resp"),
      ],
      max_tokens=10,
      compact_ratio=0.5,
    )
    agent._context_fixed_tokens = 1
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.target_tokens == 5
    assert event.dropped_count == 3
    assert event.first_remaining is None


class TestCaptureCalibration:
  """_capture_calibration: fixed-overhead + density-ratio learning."""

  def _agent(self) -> MagicMock:
    agent = MagicMock()
    agent._context_fixed_tokens = None
    agent._context_ratio = 1.0
    agent._context_char4_at_capture = None
    agent._context_last_input_tokens = None
    agent.context = BaseContextManager()
    agent.context._messages = [_msg("user", "abcdefgh")]  # 8 chars → char4 = 2
    return agent

  def test_first_capture_learns_fixed_tokens(self) -> None:
    """First capture: fixed = server − char4; ratio stays default."""
    agent = self._agent()
    _capture_calibration(agent, 102)  # 102 − 2 = 100 fixed
    assert agent._context_fixed_tokens == 100
    assert agent._context_ratio == 1.0
    assert agent._context_last_input_tokens == 102
    assert agent._context_char4_at_capture == 2

  def test_second_capture_learns_ratio_from_delta(self) -> None:
    """Growth deltas yield observed density: Δserver / Δchar4, EMA-blended."""
    agent = self._agent()
    _capture_calibration(agent, 102)  # fixed=100, char4 base=2
    # Content grows: 8 → 56 chars (char4 2 → 14, Δ=12); server 102 → 150
    # (Δ=48) → observed density 48/12 = 4.0.
    agent.context._messages = [
      _msg("user", "abcdefgh"),
      _msg("assistant", "x" * 48),
    ]
    _capture_calibration(agent, 150)
    assert agent._context_ratio == pytest.approx(1.0 * 0.5 + 4.0 * 0.5)
    # Fixed re-derived from this capture: 150 − 2.5 × 14 = 115.
    assert agent._context_fixed_tokens == 115

  def test_ratio_skipped_when_char4_shrinks(self) -> None:
    """A char4 shrink means a truncation happened — ratio is not learned."""
    agent = self._agent()
    _capture_calibration(agent, 102)
    # char4 drops from 2 to 1 (content replaced by shorter content).
    agent.context._messages = [_msg("user", "abcd")]
    _capture_calibration(agent, 99)
    assert agent._context_ratio == 1.0  # untouched
    assert agent._context_last_input_tokens == 99

  def test_calibrated_estimate_combines_fixed_and_ratio(self) -> None:
    """_calibrated_estimate = fixed + ratio × char4(messages)."""
    agent = self._agent()
    agent._context_fixed_tokens = 100
    agent._context_ratio = 2.0
    estimate = _calibrated_estimate(agent, agent.context.get_context())
    assert estimate == 100 + 2 * 2

  def test_calibrated_estimate_none_without_capture(self) -> None:
    """No server capture yet → None (caller falls back to heuristic)."""
    agent = self._agent()
    assert _calibrated_estimate(agent, agent.context.get_context()) is None
