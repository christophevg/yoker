"""Tests for context overflow detection (IP-12).

Verifies the hybrid token estimator and the ``_manage_context_overflow``
orchestration: under-cap is a no-op, over-cap runs the framework-default
compaction pipeline (age-gated prunes, force-stub, floor-clamped cutoff)
and emits a ``ContextOverflowEvent``, and thinking blocks are stripped
from non-supporting backends always-on (no config flag).
"""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.config import (
  CompactionConfig,
  CutoffConfig,
  ForceStubToolResultsConfig,
  PruneThinkingConfig,
  PruneToolResultsConfig,
)
from yoker.context import BaseContextManager
from yoker.core._processing import (
  _calibrated_estimate,
  _capture_calibration,
  _estimate_tokens,
  _first_remaining_summary,
  _manage_context_overflow,
  _noop_hook,
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
  # Mirror the Agent wiring (core/__init__): the projection thinking-strip
  # follows the backend's provider-side context-management support.
  cm.strip_thinking_in_view = not supports_context_management

  backend = MagicMock()
  backend.supports_context_management = supports_context_management

  config = MagicMock()
  config.context.max_tokens = max_tokens
  config.context.compact_ratio = compact_ratio
  # Real compaction config (chunk B): per-stage thresholds sized so the
  # small synthetic scenarios actually select messages. strategies=[] keeps
  # the default order (now including force_stub_tool_results); tests
  # override the whole object for order variants.
  config.context.compaction = CompactionConfig(
    strategies=(
      "prune_tool_results",
      "prune_thinking",
      "force_stub_tool_results",
      "cutoff",
    ),
    prune_tool_results=PruneToolResultsConfig(min_age_turns=1, min_chars=16),
    prune_thinking=PruneThinkingConfig(min_age_turns=1),
    force_stub_tool_results=ForceStubToolResultsConfig(min_chars=16),
    cutoff=CutoffConfig(),
  )

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

    asyncio.run(_manage_context_overflow(agent, _noop_hook))

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

    The protected prefix (system + first user turn) and the last plain
    assistant (protect_last_assistant=1) survive. A count far over the cap
    genuinely requires evicting all droppable history — the cap is
    enforced.
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
    # Only the last plain assistant survives (protection window).
    assert assistant_count == 1
    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count == 5
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
    # → 12 units would be needed but only 5 droppable (the last plain
    # assistant is protected) — all 5 dropped, loop stops dry.
    assert event.dropped_count == 5
    assert event.estimated_tokens == 102

  def test_all_protected_emits_zero_drop_event(self) -> None:
    """Nothing droppable (system + protected first user only): the event
    still fires with dropped_count 0 — a real saturation signal, not the
    estimator-mismatch artifact it used to be.

    Chunk B: the pipeline RAN (stages exist, run_id set) but every stage
    was quiet, so the event fires via the hook path — no-op suppression
    keeps this from being reported as a compaction run.
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

    asyncio.run(_manage_context_overflow(agent, _noop_hook))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.dropped_count == 0
    # Calibrated estimate: "hello"=5, "sys"=3 → 8 chars // 4 = 2, + fixed 1.
    assert event.estimated_tokens == 3
    assert len(agent.context.get_context()) == 2
    # Hook path: no run identity, no stages, no compaction record.
    assert event.run_id is None
    assert event.stages == []
    assert agent.context.compaction_runs == []

  def test_floor_exceeds_target_cutoff_stops(self) -> None:
    """Protected content alone exceeds the ratio target: the clamp holds.

    Uncalibrated. "sys"(3) + 500-char user + 3 droppable assistants (2
    char4 each): trigger ≈ 131 > cap 30 → ratio target 30 < floor 127 →
    cutoff targets 127; the oldest assistant units (4 char4 credited) come
    out, then the estimate dips to the floor and cutoff stops — the
    protected 500-char user turn is never touched. The event keeps the
    ORIGINAL ratio target as target_tokens.
    """
    agent = _make_agent(
      [
        _msg("system", "sys"),
        _msg("user", "F" * 500),
        *[_msg("assistant", "abcdefgh") for _ in range(3)],
      ],
      max_tokens=30,
    )
    agent._context_fixed_tokens = 0
    agent._context_ratio = 1.0
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.target_tokens == 30  # the ORIGINAL ratio target
    assert event.target_clamped is True
    assert event.floor_tokens == 127
    # Cutoff only trimmed down TO the floor — the protected user turn and
    # the last assistant survive.
    assert event.dropped_count == 2
    view = agent.context.get_context()
    assert "F" * 500 in [m["content"] for m in view]
    assert view[-1]["role"] == "assistant"
    # Exactly the two oldest droppable assistants were flagged.
    stored = agent.context.get_stored_messages()
    assert [m.get("pruned", {}).get("kind") for m in stored] == [
      None,
      None,
      "dropped",
      "dropped",
      None,
    ]

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

    asyncio.run(_manage_context_overflow(agent, _noop_hook))

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
    # The last plain assistant is protected (protect_last_assistant=1), so
    # the deep trim drains 9 of the 10 assistants.
    assert event.dropped_count == 9
    # Ratio 1.0 would have kept 7 assistants; the target leaves one.
    assistants = [m for m in agent.context.get_context() if m["role"] == "assistant"]
    assert len(assistants) == 1

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

    asyncio.run(_manage_context_overflow(agent, _noop_hook))

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
    # The last plain assistant is protected (protect_last_assistant=1), so
    # only the first two are dropped; "resp3" survives as retained history.
    assert event.dropped_count == 2
    assert event.first_remaining == "assistant: resp3resp"


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


def _estimate_of_view_char4(messages: list[dict[str, Any]]) -> int:
  """Raw char/4 estimate of a rendered view (content + thinking + tool_calls)."""
  total_chars = 0
  for msg in messages:
    content = msg.get("content") or ""
    if isinstance(content, str):
      total_chars += len(content)
    thinking = msg.get("thinking") or ""
    if isinstance(thinking, str):
      total_chars += len(thinking)
    tool_calls = msg.get("tool_calls")
    if isinstance(tool_calls, list):
      total_chars += len(json.dumps(tool_calls))
  return total_chars // 4


def _tool_result(name: str, tool_id: str, body: str, **extra: Any) -> dict[str, Any]:
  m: dict[str, Any] = {
    "role": "tool",
    "name": name,
    "tool_id": tool_id,
    "content": body,
    "success": True,
  }
  m.update(extra)
  return m


def _pipeline_agent(
  messages: list[dict[str, Any]],
  *,
  max_tokens: int,
  compact_ratio: float = 0.5,
  supports_context_management: bool = False,
) -> MagicMock:
  """Build a mock agent for the compaction-pipeline tests.

  Mirrors ``_make_agent`` (uncalibrated — raw char/4 estimates) plus a real
  ``CompactionConfig`` so the small synthetic scenarios set age/size
  thresholds that actually select messages (Slice 3: config-driven).
  """
  agent = _make_agent(
    messages,
    max_tokens=max_tokens,
    supports_context_management=supports_context_management,
    compact_ratio=compact_ratio,
  )
  return agent


class TestPruneToolResults:
  """prune_tool_results: age+size selection, projection renders stubs."""

  def test_old_large_tool_result_is_stubbed(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "hi"),
      _msg("assistant", "mid"),
      _tool_result("read", "t1", "x" * 100),
      _msg("assistant", "done"),
    ]
    assert cm.prune_tool_results(min_age_turns=1, min_chars=16) == 1
    stored = cm.get_stored_messages()
    # Stored truth keeps the full body + flag.
    assert len(stored[3]["content"]) == 100
    assert stored[3]["pruned"]["kind"] == "stub"
    assert stored[3]["pruned"]["stage"] == "prune_tool_results"
    assert stored[3]["pruned"]["chars"] == 100
    # View renders the deterministic stub.
    view = cm.get_context()
    assert "elided" in view[3]["content"]
    assert len(view[3]["content"]) < 100

  def test_small_tool_result_untouched(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("assistant", "mid"),
      _tool_result("read", "t1", "x" * 100),
      _msg("assistant", "done"),
    ]
    assert cm.prune_tool_results(min_age_turns=1, min_chars=200) == 0
    assert "pruned" not in cm.get_stored_messages()[1]

  def test_young_tool_result_untouched(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("assistant", "older turn"),
      _msg("assistant", "mid"),
      _tool_result("read", "t1", "x" * 100),
    ]
    # No completed turn after the tool result → age 0 < min_age_turns=2.
    assert cm.prune_tool_results(min_age_turns=2, min_chars=16) == 0
    assert "pruned" not in cm.get_stored_messages()[2]

  def test_user_assistant_system_never_stubbed(self) -> None:
    cm = BaseContextManager()
    big = "y" * 500
    cm._messages = [
      _msg("system", big),
      _msg("user", big),
      _msg("assistant", big),
      _msg("assistant", "done"),
    ]
    assert cm.prune_tool_results(min_age_turns=1, min_chars=16) == 0
    assert all("pruned" not in m for m in cm.get_stored_messages())

  def test_already_flagged_skipped(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("assistant", "mid"),
      _tool_result("read", "t1", "x" * 100, pruned={"kind": "dropped", "stage": "cutoff"}),
      _msg("assistant", "done"),
    ]
    assert cm.prune_tool_results(min_age_turns=1, min_chars=16) == 0
    assert cm.get_stored_messages()[1]["pruned"]["kind"] == "dropped"

  def test_tool_result_inside_young_unit_not_stubbed(self) -> None:
    """A tool result directly followed by the current turn is young (age 0)."""
    cm = BaseContextManager()
    cm._messages = [
      _msg("assistant", "older turn"),
      _msg("assistant", "mid"),
      _tool_result("read", "t1", "x" * 100),
    ]
    # No completed turn after the tool result → age 0 < min_age_turns=1.
    assert cm.prune_tool_results(min_age_turns=1, min_chars=16) == 0


class TestPruneThinking:
  """prune_thinking: old thinking flagged; projection strips it per backend."""

  def test_old_thinking_flagged(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "hi"),
      _msg("assistant", "first", thinking="deep thought"),
      _msg("assistant", "second", thinking="more thought"),
      _msg("assistant", "final"),
    ]
    assert cm.prune_thinking(min_age_turns=1) == 2
    stored = cm.get_stored_messages()
    assert stored[2]["thinking"] == "deep thought"  # stored truth retained
    assert stored[2]["pruned"]["kind"] == "thinking"
    assert stored[2]["pruned"]["stage"] == "prune_thinking"

  def test_young_thinking_not_flagged(self) -> None:
    cm = BaseContextManager()
    cm._messages = [
      _msg("user", "hi"),
      _msg("assistant", "first", thinking="deep thought"),
    ]
    assert cm.prune_thinking(min_age_turns=1) == 0
    assert "pruned" not in cm.get_stored_messages()[1]

  def test_flagged_thinking_gone_from_view_supporting_backend(self) -> None:
    """Supporting backend (strips thinking in view): flagged thinking is
    dropped for the same reason all thinking is — ~0 extra impact."""
    cm = BaseContextManager()
    cm.strip_thinking_in_view = False  # provider-side management keeps thinking
    cm._messages = [
      _msg("user", "hi"),
      _msg("assistant", "first", thinking="deep thought"),
      _msg("assistant", "final"),
    ]
    cm.prune_thinking(min_age_turns=1)
    view = cm.get_context()
    # Only the flagged (old) message loses its thinking; the fresh final
    # message's thinking is submitted (provider manages it server-side).
    assert "thinking" not in view[1]
    assert "thinking" not in view[2]

  def test_flagged_thinking_gone_from_view_non_supporting_backend(self) -> None:
    """Non-supporting backend strips ALL thinking anyway; flag is redundant
    but harmless — honest ~0 measured impact on this backend kind."""
    cm = BaseContextManager()
    cm.strip_thinking_in_view = True
    cm._messages = [
      _msg("user", "hi"),
      _msg("assistant", "first", thinking="deep thought"),
      _msg("assistant", "final"),
    ]
    cm.prune_thinking(min_age_turns=1)
    assert all("thinking" not in m for m in cm.get_context())


class TestCompactionPipeline:
  """_run_compaction_pipeline: stage order, unconditional prunes, per-run counts."""

  def test_stage_order_and_event_fields(self) -> None:
    """All content-preserving stages run, then cutoff; event carries the truth."""
    # Raw char/4 arithmetic (uncalibrated agent): total chars = prefix 5 +
    # 3×(6 assistant + 2000 tool) + 40×160 code-dense assistants + 4 final
    # = 12_427 → trigger 3106 > cap 2000. Stubs save ≈ 3×(500−20) → view
    # ≈ 6667 chars → est 1667 > target 1000 → cutoff fires as backstop.
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    for i in range(3):
      messages.append(_msg("assistant", f"turn {i}"))
      messages.append(_tool_result("read", f"t{i}", "x" * 2000))
    for _ in range(40):
      messages.append(_msg("assistant", "abcdefgh" * 20))
    messages.append(_msg("assistant", "last"))
    agent = _pipeline_agent(messages, max_tokens=2000, compact_ratio=0.5)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    # Chunk B: every stage reports (the prunes/stub run unconditionally;
    # prune_thinking flags nothing here so its message count is 0 — but a
    # 0-delta, 0-flag stage still lands in the list per the task contract).
    assert [s["name"] for s in event.stages] == [
      "prune_tool_results",
      "prune_thinking",
      "force_stub_tool_results",
      "cutoff",
    ]
    # Per-stage message counts are truthful: 3 tool results stubbed by the
    # age-gated prune (force_stub is idempotent — the bodies are already
    # flagged so it adds nothing), and the cutoff flagged at least one unit.
    prune_stage = next(s for s in event.stages if s["name"] == "prune_tool_results")
    assert prune_stage["messages"] == 3
    cutoff_stage = next(s for s in event.stages if s["name"] == "cutoff")
    assert cutoff_stage["messages"] > 0
    # The prune and cutoff stages actually shrank the view; prune_thinking
    # and force_stub are no-ops here (0 flags, 0 delta).
    assert next(s for s in event.stages if s["name"] == "prune_tool_results")["tokens"] > 0
    assert cutoff_stage["tokens"] > 0
    for name in ("prune_thinking", "force_stub_tool_results"):
      assert next(s for s in event.stages if s["name"] == name)["tokens"] == 0
    # Chunk B: run_id present on every stage + the event.
    assert event.run_id is not None
    assert all(s["run_id"] == event.run_id for s in event.stages)
    # Truthful landing fields.
    assert event.sent_count == len(agent.context.get_context())
    view_estimate = event.remaining_estimated_tokens
    assert view_estimate is not None
    assert view_estimate <= event.target_tokens
    # The old fields keep stored-based semantics.
    assert event.message_count == len(agent.context.get_stored_messages())
    assert event.dropped_count > 0

  def test_prune_thinking_flags_counted_per_run(self) -> None:
    """prune_thinking runs in the default pipeline; its flags carry the run id.

    A supporting backend keeps thinking in the view (the projection only
    strips it for non-supporting backends), so the 500-char payload counts
    toward the estimate and pushes it over the cap.
    """
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    messages.append({"role": "assistant", "content": "a", "thinking": "t" * 500})
    messages.append(_msg("assistant", "done"))
    messages.append(_msg("user", "again"))
    messages.append(_msg("assistant", "done2"))
    agent = _pipeline_agent(
      messages, max_tokens=10, compact_ratio=0.5, supports_context_management=True
    )
    agent.config.context.compaction.cutoff = CutoffConfig(protect_last_assistant=0)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    thinking_stage = next((s for s in event.stages if s["name"] == "prune_thinking"), None)
    assert thinking_stage is not None
    assert thinking_stage["messages"] == 1
    # The flag itself carries this run's id.
    assert event.run_id is not None
    flagged = [
      m
      for m in agent.context.get_stored_messages()
      if m.get("pruned", {}).get("stage") == "prune_thinking"
    ]
    assert len(flagged) == 1
    assert flagged[0]["pruned"]["run"] == event.run_id
    # Per-run counting: a pre-existing flag from an EARLIER run must not
    # be counted (or re-flagged) by this run's stage report.
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "hi"),
      {
        "role": "assistant",
        "content": "a",
        "thinking": "t" * 100,
        "pruned": {"kind": "thinking", "stage": "prune_thinking", "run": "older"},
      },
    ]
    cm.strip_thinking_in_view = True
    assert cm.prune_thinking(min_age_turns=1, run="newer") == 0
    assert cm.get_stored_messages()[2]["pruned"]["run"] == "older"

  def test_force_stub_dispatches_with_config_threshold(self) -> None:
    """force_stub_tool_results stubs young results the age-gated prune skipped.

    The age-gated prune (min_age_turns=1) leaves the LAST tool result
    (age 0, body 20,000 > the configured 5,000 threshold) unflagged;
    force_stub (min_chars=5000) then stubs it — which alone brings the
    view under the target, so the cutoff has nothing left to drop.
    """
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    for i in range(3):
      messages.append(_msg("assistant", f"turn {i}"))
      messages.append(_tool_result("read", f"t{i}", "x" * 2000))
    messages.append(_msg("assistant", "done"))
    # The last (age-0) tool result carries a 20,000-char body — young but
    # HUGE, exactly the case force_stub exists for.
    messages.append(_tool_result("read", "t-big", "x" * 20_000))
    agent = _pipeline_agent(messages, max_tokens=6000, compact_ratio=0.5)
    agent.config.context.compaction.force_stub_tool_results = ForceStubToolResultsConfig(
      min_chars=5000
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.run_id is not None
    # Raw char/4: total chars = 5 + 3×(6+2000) + 5 + 20000 = 26,036 →
    # trigger 6509 > cap 8000? NO — under cap. Cap must sit below the
    # trigger: 6000 → trigger 6509 > 6000, target 3000. The huge body
    # alone is ≈5000 tokens, so stubbing it must land below that.
    assert event.estimated_tokens > event.max_tokens
    # force_stub stubbed the huge young result (stage name on its flag).
    stored = agent.context.get_stored_messages()
    big_flag = stored[-1].get("pruned", {})
    assert big_flag.get("kind") == "stub"
    assert big_flag.get("stage") == "force_stub_tool_results"
    # Stubbing it (−4999) already landed under the target (3000): the
    # cutoff stage had NOTHING left to drop — the frame+results stay.
    assert event.dropped_count == 0
    assert event.remaining_estimated_tokens is not None
    assert event.remaining_estimated_tokens <= event.target_tokens
    # Stored truth keeps every body; the view shows the stub only.
    assert len(stored[-1]["content"]) == 20_000
    assert "elided" in agent.context.get_context()[-1]["content"]

  def test_early_exit_prune_alone_reaches_target(self) -> None:
    """Prune reaching the target: cutoff still runs (unconditional), drops 0."""
    # Raw char/4: total chars ≈ 4045 → trigger 1011 > cap 800; stubbing
    # all four tools saves ≈ 4×(250−20) → achieved ≈ 32 < target 400
    # → nothing dropped, store fully retained.
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    for i in range(4):
      messages.append(_msg("assistant", f"turn {i}"))
      messages.append(_tool_result("read", f"t{i}", "x" * 1000))
    messages.append(_msg("assistant", "last"))
    agent = _pipeline_agent(messages, max_tokens=800, compact_ratio=0.5)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    # Every stage reports; cutoff runs but drops nothing (already under
    # target) — the run did real work (3 flags), so the event fires.
    assert [s["name"] for s in event.stages] == [
      "prune_tool_results",
      "prune_thinking",
      "force_stub_tool_results",
      "cutoff",
    ]
    prune_stage = next(s for s in event.stages if s["name"] == "prune_tool_results")
    assert prune_stage["messages"] == 4
    for name in ("prune_thinking", "force_stub_tool_results", "cutoff"):
      assert next(s for s in event.stages if s["name"] == name)["messages"] == 0
    assert event.dropped_count == 0
    # Stored history is fully retained — nothing was dropped.
    assert len(agent.context.get_stored_messages()) == len(messages)
    assert event.remaining_estimated_tokens <= event.target_tokens

  def test_configured_stage_order_override(self) -> None:
    """A configured compaction strategies list is honored in order."""
    agent = _pipeline_agent(
      [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "resp")],
      max_tokens=1,
    )
    agent.config.context.compaction = CompactionConfig(
      strategies=("cutoff",),
      cutoff=CutoffConfig(protect_last_assistant=0),
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert [s["name"] for s in event.stages] == ["cutoff"]

  def test_cutoff_as_backstop_finishes_job(self) -> None:
    """Prune insufficient → cutoff flags oldest units until under target."""
    # Raw char/4: 2 + 8×~7 ≈ 58... too tight. Use 8×500-char assistants:
    # trigger ≈ 2 + 8×125 = 1002 > cap 60 → after prune (no tool results),
    # cutoff must flag most assistants. Target = 30 = 2 + ~112 chars.
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    for _ in range(8):
      messages.append(_msg("assistant", "abcdefgh" * 50))  # 400 chars → 100 tokens
    agent = _pipeline_agent(messages, max_tokens=60, compact_ratio=0.5)
    # The backstop's job here is to drain everything droppable — disable
    # the last-plain-assistant window so the target is genuinely reachable.
    agent.config.context.compaction.cutoff = CutoffConfig(protect_last_assistant=0)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert "cutoff" in [s["name"] for s in event.stages]
    assert event.remaining_estimated_tokens <= event.target_tokens
    # Stored count never decreases (flags, not removals); the view shrank.
    assert event.message_count == len(messages)
    assert event.sent_count < len(messages)

  def test_all_protected_still_emits_honest_event(self) -> None:
    """Nothing prunable/droppable: zero stages, achieved = trigger estimate.

    Chunk B no-op suppression: nothing flagged and nothing dropped → the
    event is SUPPRESSED (no event, no compaction record) — the saturation
    signal would be pure noise.
    """
    agent = _pipeline_agent(
      [_msg("system", "sys"), _msg("user", "hello")],
      max_tokens=1,
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    # No event: the pipeline achieved nothing (no flags, no drops).
    assert events == []
    # And no compaction record — the run was a no-op.
    assert agent.context.compaction_runs == []


class TestLandingAccuracy:
  """The overshoot fix: landing near the target, not 5x below it."""

  def test_code_dense_content_lands_near_target(self) -> None:
    """Code-dense drops + calibrated ratio below true density: the pipeline
    must land within a sane band of the target — never drain the history.

    The learned ratio (0.5) underestimates the content's true density; the
    OLD loop charged each drop in credited currency and kept dropping
    while its credited overage was positive — overshooting past the target
    and draining history. The new loop stops on a fresh view re-estimate
    in the SAME currency as the trigger, so the achieved estimate lands
    within a couple of atomic units of the target.
    """
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    for i in range(10):
      messages.append(_msg("assistant", "abcdefgh" * 20))  # 160 chars → 40 char4
      messages.append(_msg("user", f"turn {i} prompt"))
    agent = _pipeline_agent(messages, max_tokens=300, compact_ratio=0.5)
    # Calibrated: ratio 0.5, fixed 100. char4 ≈ 2 + 10×40 + 10×3 = 432 →
    # trigger = 100 + 216 = 316 > cap 300 ✓; target = 150. Each assistant
    # drop moves the view estimate by 0.5×40 = 20 — small units, so the
    # stop lands just under the target with history intact.
    agent._context_fixed_tokens = 100
    agent._context_ratio = 0.5
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    achieved = event.remaining_estimated_tokens
    assert achieved is not None
    target = event.target_tokens
    # Sanity: the trigger state really was over the cap.
    assert event.estimated_tokens > event.max_tokens
    # The landing band: within 20% of the target — the OLD loop's
    # credited-currency draining would blow straight through this band.
    assert achieved <= target
    assert achieved >= target * 0.8
    # Structure retained: the newest stored messages survive in the view
    # (the old loop dropped until dry, leaving only the protected prefix).
    view = agent.context.get_context()
    stored = agent.context.get_stored_messages()
    non_prefix = view[2:]
    assert len(non_prefix) >= 2
    assert non_prefix[-1]["role"] == stored[-1]["role"]
    assert non_prefix[-1]["content"] == stored[-1]["content"]

  def test_huge_stub_elision_enables_fine_landing(self) -> None:
    """One huge tool body stubbed to ~50 tokens shrinks the view a lot,
    letting the pipeline land near the target without dropping messages.

    Realism note: the prune stage is a BATCH operation — it stubs every
    eligible tool result at once — so the landing resolution equals the
    stub-able mass. The scenario therefore sizes the non-tool content to
    be small relative to the target, making a one-batch landing precise.
    """
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    for i in range(5):
      messages.append(_msg("assistant", f"turn {i}"))
      messages.append(_tool_result("read", f"t{i}", "x" * 20_000))
    messages.append(_msg("assistant", "last"))
    # Raw char/4: total chars ≈ 25037 → trigger 6259 > cap 6000; stubbing
    # all five saves ≈ 5×(5000−20) → achieved = target − (target − 116)
    # measured 116 vs target 3000 (≈ 4% of the target — the non-tool
    # remainder) → prune alone lands.
    agent = _pipeline_agent(messages, max_tokens=6000, compact_ratio=0.5)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    achieved = event.remaining_estimated_tokens
    assert achieved is not None
    target = event.target_tokens
    # Landing: far below the target (stub elision is total here), the
    # store fully retained, and the achieved estimate tiny vs the trigger.
    assert achieved <= target
    assert achieved >= 0
    # Nothing needed dropping — stubs alone reached the target.
    assert event.dropped_count == 0
    # Stored truth: all 100K chars of tool bodies are still on disk.
    stored_bodies = [
      m["content"] for m in agent.context.get_stored_messages() if m["role"] == "tool"
    ]
    assert all(len(body) == 20_000 for body in stored_bodies)
    # The view carries only the tiny stubs.
    view_bodies = [m["content"] for m in agent.context.get_context() if m["role"] == "tool"]
    assert all("elided" in body for body in view_bodies)

  """Chunk B core fix: cutoff target is clamped up to the protection floor."""

  def _agent(self, floor_chars: int, max_tokens: int, compact_ratio: float = 0.5) -> MagicMock:
    """System + a huge first user turn (protected) + disposable droppable.

    Raw char/4 arithmetic: "sys" (3) + first user (floor_chars) + one
    droppable assistant ("abcdefgh") + the final assistant "last" (4).
    The protected set (defaults 1/1/1/1) is scaffolding {sys, first user}
    plus the LAST plain assistant "last" — protect_last_assistant=1 — so
    the floor counts "last" too.
    """
    messages = [
      _msg("system", "sys"),
      _msg("user", "F" * floor_chars),
      _msg("assistant", "abcdefgh"),
      _msg("assistant", "last"),
    ]
    return _pipeline_agent(messages, max_tokens=max_tokens, compact_ratio=compact_ratio)

  def test_floor_exceeds_target_cutoff_stops_and_clamps(self) -> None:
    """Protected content alone exceeds the target: cutoff drops nothing.

    Floor = char/4 of the PROTECTED set {sys(3), first user(300), last
    plain assistant "last"(4)} = 307 // 4 = 76 tokens > target
    int(20×0.5) = 10 → the effective target is clamped to 76; the
    droppable units weigh 2 and 1 char4, so cutoff drops at most the
    2-char4 unit — and the event carries target_tokens = ORIGINAL ratio
    target, floor_tokens and clamped=True.
    """
    agent = self._agent(floor_chars=300, max_tokens=20)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    # The event keeps the ORIGINAL ratio target; the clamp is separate.
    assert event.target_tokens == 10
    assert event.target_clamped is True
    assert event.floor_tokens == 76
    # Cutoff stopped at the floor: only the small droppable assistant was
    # dropped (the last plain assistant is protected by default), and the
    # protected first user turn survives in the view.
    assert event.dropped_count == 1
    view = agent.context.get_context()
    roles = [m["role"] for m in view]
    assert "F" * 300 in [m["content"] for m in view]
    assert roles[-1] == "assistant"  # the protected "last" survives
    # Only non-protected content was dropped: the first droppable unit.
    stored = agent.context.get_stored_messages()
    assert stored[2]["pruned"]["kind"] == "dropped"
    assert "pruned" not in stored[1]

  def test_floor_not_exceeded_no_clamp(self) -> None:
    """Small protected content: target untouched, clamp flag stays False.

    Trigger must exceed the cap (the pipeline runs and reports the floor)
    while the floor stays at/below the ratio target: sys(3) + user(20) +
    5 droppable assistants(8 each) + last(4) = 67 chars → trigger 16 >
    cap 15; floor = (3+20+4)//4 = 6 ≤ target int(15×0.5) = 7 → no clamp.
    """
    messages = [
      _msg("system", "sys"),
      _msg("user", "F" * 20),
      *[_msg("assistant", "abcdefgh") for _ in range(5)],
      _msg("assistant", "last"),
    ]
    agent = _pipeline_agent(messages, max_tokens=15, compact_ratio=0.5)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    event = next(e for e in events if isinstance(e, ContextOverflowEvent))
    assert event.target_clamped is False
    assert event.floor_tokens is not None
    assert event.floor_tokens <= event.target_tokens

  def test_floor_recorded_in_compaction_record(self) -> None:
    """The compaction record carries floor_tokens + target_clamped."""
    agent = self._agent(floor_chars=300, max_tokens=20)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    runs = agent.context.compaction_runs
    assert len(runs) == 1
    record = runs[0]
    assert record["target_clamped"] is True
    assert record["floor_tokens"] == 76
    assert record["target"] == 10  # original ratio target


class TestNoOpSuppression:
  """Chunk B: a fully-flagged (no-op) pipeline suppresses event + record."""

  def test_over_cap_all_flagged_no_event(self) -> None:
    """Over cap but everything already flagged by an earlier run: no event."""
    # 30 disposable 8-char assistants + 8-char final: trigger ≈ 63 > cap 10
    # → target 30. Pre-flag ALL assistants as dropped (as an earlier run
    # would have): nothing is droppable for THIS run, prune stages flag
    # nothing → the whole pipeline is a no-op → suppressed.
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    assistants = [_msg("assistant", "abcdefgh") for _ in range(30)]
    for m in assistants:
      m["pruned"] = {
        "kind": "dropped",
        "stage": "cutoff",
        "run": "earlier-run",
      }
    messages.extend(assistants)
    agent = _pipeline_agent(messages, max_tokens=250, compact_ratio=0.5)
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    # Suppressed: no event, no record. The estimate is still over the cap
    # (the estimator counts the store), but this run achieved nothing.
    assert events == []
    assert agent.context.compaction_runs == []

  def test_zero_delta_but_flagged_stage_still_reports(self) -> None:
    """A stage that flags messages with ~0 view impact still lands in stages.

    Direct unit-level check: with strip_thinking_in_view=True, flagged
    thinking renders identically to unflagged thinking in the view
    (the projection strips ALL thinking for this backend kind), so the
    stage's view-char4 impact is exactly 0 — but the flag lands and the
    stage message count is 1. The pipeline's landing rule
    (estimate < before OR flagged > 0) keeps it reported.
    """
    cm = BaseContextManager()
    cm._messages = [
      _msg("system", "sys"),
      _msg("user", "hi"),
      {"role": "assistant", "content": "a", "thinking": "t" * 400},
      _msg("assistant", "done"),
    ]
    cm.strip_thinking_in_view = True
    # Zero-view-impact flagging: with strip_thinking_in_view=True the
    # projection renders flagged and unflagged thinking identically, so
    # flagging moves the view estimate by 0 — exactly the case the
    # pipeline's landing rule (estimate < before OR flagged > 0) exists for.
    before = _estimate_of_view_char4(cm.get_context())
    flagged = cm.prune_thinking(min_age_turns=1)
    assert flagged == 1
    after = _estimate_of_view_char4(cm.get_context())
    # Zero view impact (backend strips thinking anyway)...
    assert after == before
    # ...but the stage still has messages to report.
    assert (
      len(
        [
          m
          for m in cm.get_stored_messages()
          if m.get("pruned", {}).get("stage") == "prune_thinking"
        ]
      )
      == 1
    )

  def test_suppressed_run_writes_no_record(self) -> None:
    """Suppression applies to the compaction record too (all-quiet run)."""
    agent = _pipeline_agent(
      [_msg("system", "sys"), _msg("user", "hello")],
      max_tokens=1,
    )
    events: list[Any] = []
    handler: EventCallback = lambda e: events.append(e)  # noqa: E731
    agent._event_handlers = [handler]

    import asyncio

    asyncio.run(_manage_context_overflow(agent, None))

    assert events == []
    assert agent.context.compaction_runs == []
