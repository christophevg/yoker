"""Tests for the on_context_overflow hook (IP-12).

Verifies ``_validate_hook_output`` (shape, role=system preservation,
tool-call/tool-result pairing) and ``_apply_overflow_hook`` (applies a
valid replacement, falls back on None/invalid/exception). The hook ships
as ``None`` in ``process_message``; these tests exercise the machinery
directly.
"""

from typing import Any
from unittest.mock import MagicMock

from yoker.context import BaseContextManager
from yoker.core._processing import (
  OverflowContext,
  _apply_overflow_hook,
  _validate_hook_output,
)


def _msg(role: str, content: str, **extra: Any) -> dict[str, Any]:
  m: dict[str, Any] = {"role": role, "content": content}
  m.update(extra)
  return m


def _tool_call(call_id: str = "call_1") -> dict[str, Any]:
  return {
    "role": "assistant",
    "content": "",
    "tool_calls": [{"id": call_id, "name": "read", "arguments": {}}],
  }


def _tool_result(call_id: str = "call_1") -> dict[str, Any]:
  return {
    "role": "tool",
    "tool_id": call_id,
    "name": "read",
    "content": "data",
    "success": True,
  }


class TestValidateHookOutput:
  """_validate_hook_output enforces shape, system preservation, and pairing."""

  def test_valid_replacement_passes(self) -> None:
    """A well-formed replacement with intact pairing passes validation."""
    original = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "resp")]
    replacement = [_msg("system", "sys"), _msg("user", "hi")]
    assert _validate_hook_output(original, replacement) is True

  def test_non_list_replacement_fails(self) -> None:
    """A non-list replacement fails validation."""
    original = [_msg("system", "sys")]
    assert _validate_hook_output(original, "not a list") is False  # type: ignore[arg-type]

  def test_non_dict_item_fails(self) -> None:
    """A non-dict item in the replacement fails validation."""
    original = [_msg("system", "sys")]
    assert _validate_hook_output(original, ["not a dict"]) is False  # type: ignore[list-item]

  def test_item_missing_role_fails(self) -> None:
    """An item without a role key fails validation."""
    original = [_msg("system", "sys")]
    assert _validate_hook_output(original, [{"content": "no role"}]) is False

  def test_dropped_system_message_fails(self) -> None:
    """Dropping a role=system message fails validation."""
    original = [_msg("system", "sys"), _msg("user", "hi")]
    replacement = [_msg("user", "hi")]
    assert _validate_hook_output(original, replacement) is False

  def test_kept_system_count_passes(self) -> None:
    """Keeping all system messages (even with drops elsewhere) passes."""
    original = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "r")]
    replacement = [_msg("system", "sys")]
    assert _validate_hook_output(original, replacement) is True

  def test_orphaned_tool_result_fails(self) -> None:
    """A tool result without a matching tool call fails validation."""
    original = [_msg("system", "sys")]
    replacement = [_msg("system", "sys"), _tool_result("call_x")]
    assert _validate_hook_output(original, replacement) is False

  def test_dangling_tool_call_fails(self) -> None:
    """A tool call without a matching tool result fails validation."""
    original = [_msg("system", "sys")]
    replacement = [_msg("system", "sys"), _tool_call("call_1")]
    assert _validate_hook_output(original, replacement) is False

  def test_paired_tool_call_and_result_passes(self) -> None:
    """A matched tool_call + tool_result pair passes validation."""
    original = [_msg("system", "sys")]
    replacement = [_msg("system", "sys"), _tool_call("call_1"), _tool_result("call_1")]
    assert _validate_hook_output(original, replacement) is True


def _make_agent(messages: list[dict[str, Any]]) -> MagicMock:
  """Build a mock agent whose context holds ``messages``."""
  cm = BaseContextManager()
  cm._messages = list(messages)
  agent = MagicMock()
  agent.context = cm
  return agent


class TestApplyOverflowHook:
  """_apply_overflow_hook: applies valid output, falls back on failure."""

  def test_valid_replacement_is_applied(self) -> None:
    """A valid replacement replaces the context's messages."""
    original = [
      _msg("system", "sys"),
      _msg("user", "first"),
      _msg("assistant", "resp1"),
      _msg("user", "second"),
      _msg("assistant", "resp2"),
    ]
    agent = _make_agent(original)

    def hook(_payload: OverflowContext) -> list[dict[str, Any]]:
      # Drop one droppable message ("resp1").
      return [
        _msg("system", "sys"),
        _msg("user", "first"),
        _msg("user", "second"),
        _msg("assistant", "resp2"),
      ]

    dropped = _apply_overflow_hook(agent, hook, messages=original, estimated=500, max_tokens=100)
    assert dropped == 1
    contents = [m["content"] for m in agent.context.get_context()]
    assert "resp1" not in contents
    assert "resp2" in contents

  def test_none_return_drops_nothing(self) -> None:
    """A None return yields dropped=0 and leaves context unchanged."""
    original = [_msg("system", "sys"), _msg("user", "hi")]
    agent = _make_agent(original)

    def hook(_payload: OverflowContext) -> list[dict[str, Any]] | None:
      return None

    dropped = _apply_overflow_hook(agent, hook, messages=original, estimated=500, max_tokens=100)
    assert dropped == 0
    assert len(agent.context.get_context()) == 2

  def test_invalid_replacement_drops_nothing(self) -> None:
    """An invalid replacement (drops system) is rejected; context unchanged."""
    original = [_msg("system", "sys"), _msg("user", "hi")]
    agent = _make_agent(original)

    def hook(_payload: OverflowContext) -> list[dict[str, Any]]:
      # Invalid: drops the system message.
      return [_msg("user", "hi")]

    dropped = _apply_overflow_hook(agent, hook, messages=original, estimated=500, max_tokens=100)
    assert dropped == 0
    # Context unchanged.
    roles = [m["role"] for m in agent.context.get_context()]
    assert "system" in roles

  def test_hook_exception_drops_nothing(self) -> None:
    """A raising hook yields dropped=0 and leaves context unchanged."""
    original = [_msg("system", "sys"), _msg("user", "hi")]
    agent = _make_agent(original)

    def hook(_payload: OverflowContext) -> list[dict[str, Any]]:
      raise RuntimeError("hook blew up")

    dropped = _apply_overflow_hook(agent, hook, messages=original, estimated=500, max_tokens=100)
    assert dropped == 0
    assert len(agent.context.get_context()) == 2

  def test_hook_receives_payload(self) -> None:
    """The hook receives message_count, estimated_tokens, max_tokens, messages."""
    original = [_msg("system", "sys"), _msg("user", "hi")]
    agent = _make_agent(original)
    received: dict[str, Any] = {}

    def hook(payload: OverflowContext) -> list[dict[str, Any]] | None:
      received.update(payload)
      return None

    _apply_overflow_hook(agent, hook, messages=original, estimated=42, max_tokens=10)
    assert received["message_count"] == 2
    assert received["estimated_tokens"] == 42
    assert received["max_tokens"] == 10
    assert received["messages"] is original
