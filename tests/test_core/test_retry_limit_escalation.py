"""Tests for retry-limit escalation in the tool loop (0.12.0 Tier 3).

Verifies that consecutive failed tool calls trigger a one-time system-side
escalation note telling the model to stop retrying the same approach:

1. Counter: failures increment, successes reset to 0 (and clear the
   injected flag).
2. Injection: the note is added as a system message when the threshold
   (``agent.max_consecutive_tool_failures``) is reached — exactly once
   per escalation cycle.
3. Re-trigger: after a success resets the state, a new failure streak
   re-triggers the note.
4. Disabled: ``max_consecutive_tool_failures = 0`` never injects.
5. Config validation: negative values rejected.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from yoker.config import AgentConfig
from yoker.core._processing import (
  _EscalationState,
  _execute_tool_calls,
  _maybe_inject_escalation,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def failing_tool(path: str) -> str:
  """Return a test result (never actually called in these tests)."""
  return path


def make_agent(limit: int) -> MagicMock:
  """Build a mock agent with the escalation limit configured."""
  agent = MagicMock()
  agent.config.agent.max_consecutive_tool_failures = limit
  return agent


def make_call(name: str = "failing_tool", call_id: str = "call_1") -> MagicMock:
  """Build a minimal tool-call object.

  ``parse_error`` is set to None explicitly — a bare MagicMock attribute
  would be truthy and take the parse-error branch instead of executing
  the tool.
  """
  call = MagicMock()
  call.id = call_id
  call.parse_error = None
  call.function.name = name
  call.function.arguments = {"path": "x"}
  return call


def make_calls(n: int, name: str = "failing_tool") -> list[MagicMock]:
  """Build n tool calls with unique ids (duplicates get deduplicated)."""
  return [make_call(name, f"call_{i}") for i in range(n)]


def make_failing_run(monkeypatch: pytest.MonkeyPatch) -> list[str]:
  """Patch _run_tool to record failures; returns the error messages used."""
  errors = ["Error: boom"]

  async def fake_run(agent: Any, tool_name: str, tool_args: dict) -> tuple:
    return errors[0], False, None

  monkeypatch.setattr("yoker.core._processing._run_tool", fake_run)
  return errors


def make_succeeding_run(monkeypatch: pytest.MonkeyPatch) -> None:
  """Patch _run_tool to succeed."""

  async def fake_run(agent: Any, tool_name: str, tool_args: dict) -> tuple:
    return "ok", True, MagicMock(success=True)

  monkeypatch.setattr("yoker.core._processing._run_tool", fake_run)


# ---------------------------------------------------------------------------
# Counter behavior (_execute_single_tool_call via _execute_tool_calls)
# ---------------------------------------------------------------------------


class TestFailureCounter:
  """Consecutive-failure counting and success reset."""

  @pytest.mark.asyncio
  async def test_failures_increment_counter(self, monkeypatch: pytest.MonkeyPatch) -> None:
    make_failing_run(monkeypatch)
    agent = make_agent(limit=5)  # high limit: no injection fires
    escalation = _EscalationState()

    await _execute_tool_calls(agent, make_calls(2), "", escalation=escalation)

    assert escalation.consecutive_failures == 2
    assert escalation.injected is False

  @pytest.mark.asyncio
  async def test_success_resets_counter_and_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
    make_failing_run(monkeypatch)
    agent = make_agent(limit=2)
    escalation = _EscalationState()
    # Simulate an already-escalated state.
    escalation.consecutive_failures = 2
    escalation.injected = True

    # One success resets both fields.
    make_succeeding_run(monkeypatch)
    await _execute_tool_calls(agent, make_calls(1), "", escalation=escalation)

    assert escalation.consecutive_failures == 0
    assert escalation.injected is False

  @pytest.mark.asyncio
  async def test_no_escalation_state_is_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing callers without escalation state keep working."""
    make_failing_run(monkeypatch)
    agent = make_agent(limit=3)

    await _execute_tool_calls(agent, make_calls(1), "")

    # Nothing to assert on the state — just must not raise.


# ---------------------------------------------------------------------------
# Injection (_maybe_inject_escalation)
# ---------------------------------------------------------------------------


class TestEscalationInjection:
  """System-side note injection at the configured threshold."""

  @pytest.mark.asyncio
  async def test_injects_at_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
    make_failing_run(monkeypatch)
    agent = make_agent(limit=3)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState()

    await _execute_tool_calls(agent, make_calls(3), "", escalation=escalation)

    agent.context.add_message.assert_called_once()
    role, note = agent.context.add_message.call_args.args
    assert role == "system"
    assert "3 tool calls failed" in note
    assert "Stop retrying" in note
    assert escalation.injected is True

  @pytest.mark.asyncio
  async def test_injects_only_once_per_cycle(self, monkeypatch: pytest.MonkeyPatch) -> None:
    make_failing_run(monkeypatch)
    agent = make_agent(limit=2)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState()

    await _execute_tool_calls(agent, make_calls(3), "", escalation=escalation)

    # 3 failures, limit 2 → note fires after the 2nd, not again on the 3rd.
    agent.context.add_message.assert_called_once()
    assert escalation.consecutive_failures == 3

  @pytest.mark.asyncio
  async def test_retriggers_after_reset(self, monkeypatch: pytest.MonkeyPatch) -> None:
    """After a success resets the state, a new streak re-triggers the note."""
    make_failing_run(monkeypatch)
    agent = make_agent(limit=2)
    agent.context.add_message = MagicMock()

    # First streak: 2 failures → note fires.
    escalation = _EscalationState()
    await _execute_tool_calls(agent, make_calls(2), "", escalation=escalation)
    assert agent.context.add_message.call_count == 1

    # Success resets everything.
    make_succeeding_run(monkeypatch)
    await _execute_tool_calls(agent, make_calls(1), "", escalation=escalation)
    assert escalation.consecutive_failures == 0
    assert escalation.injected is False

    # Second streak: 2 more failures → note fires again.
    make_failing_run(monkeypatch)
    await _execute_tool_calls(agent, make_calls(2), "", escalation=escalation)
    assert agent.context.add_message.call_count == 2
    assert "2 tool calls failed" in agent.context.add_message.call_args.args[1]

  @pytest.mark.asyncio
  async def test_disabled_when_limit_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
    make_failing_run(monkeypatch)
    agent = make_agent(limit=0)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState()

    await _execute_tool_calls(agent, make_calls(4), "", escalation=escalation)

    agent.context.add_message.assert_not_called()
    assert escalation.consecutive_failures == 4  # counter still tracked
    assert escalation.injected is False

  @pytest.mark.asyncio
  async def test_below_threshold_no_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
    make_failing_run(monkeypatch)
    agent = make_agent(limit=3)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState()

    await _execute_tool_calls(agent, make_calls(2), "", escalation=escalation)

    agent.context.add_message.assert_not_called()
    assert escalation.injected is False


class TestMaybeInjectEscalation:
  """Direct unit tests for the injection predicate."""

  def test_fires_at_threshold(self) -> None:
    agent = make_agent(limit=3)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState(consecutive_failures=3)

    _maybe_inject_escalation(agent, escalation)

    agent.context.add_message.assert_called_once_with("system", _note_with(3))
    assert escalation.injected is True

  def test_no_fire_below_threshold(self) -> None:
    agent = make_agent(limit=3)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState(consecutive_failures=2)

    _maybe_inject_escalation(agent, escalation)

    agent.context.add_message.assert_not_called()
    assert escalation.injected is False

  def test_no_fire_when_already_injected(self) -> None:
    agent = make_agent(limit=3)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState(consecutive_failures=5, injected=True)

    _maybe_inject_escalation(agent, escalation)

    agent.context.add_message.assert_not_called()

  def test_no_fire_when_disabled(self) -> None:
    agent = make_agent(limit=0)
    agent.context.add_message = MagicMock()
    escalation = _EscalationState(consecutive_failures=10)

    _maybe_inject_escalation(agent, escalation)

    agent.context.add_message.assert_not_called()
    assert escalation.injected is False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestAgentConfigValidation:
  """max_consecutive_tool_failures validation."""

  def test_default_is_three(self) -> None:
    config = AgentConfig()
    assert config.max_consecutive_tool_failures == 3

  def test_zero_allowed(self) -> None:
    config = AgentConfig(max_consecutive_tool_failures=0)
    assert config.max_consecutive_tool_failures == 0

  def test_negative_rejected(self) -> None:
    with pytest.raises(Exception, match="max_consecutive_tool_failures"):
      AgentConfig(max_consecutive_tool_failures=-1)


# ---------------------------------------------------------------------------
# Helpers used above
# ---------------------------------------------------------------------------


def _note_with(n: int) -> str:
  """Render the escalation note for n failures (mirrors the module constant)."""
  from yoker.core._processing import _TOOL_FAILURE_ESCALATION_NOTE

  return _TOOL_FAILURE_ESCALATION_NOTE.format(n=n)
