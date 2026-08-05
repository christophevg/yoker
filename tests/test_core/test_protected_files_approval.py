"""Tests for the protected-file interactive approval flow (MBI-009 T12).

Covers the processing-loop approval hook in :mod:`yoker.core._processing`
and the diff helper in :mod:`yoker.tools.diff`. The PathGuardrail simple
block is covered in ``tests/tools/test_path_guardrail_protected.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from yoker.config import Config, PermissionsConfig
from yoker.core._processing import _build_approval_diff, _maybe_block_protected
from yoker.tools.diff import generate_diff


class _FakeGuardrail:
  """Minimal stand-in for PathGuardrail exposing ``is_protected``."""

  def __init__(self, protected: bool) -> None:
    self._protected = protected
    self.interactive_approvals = False

  def is_protected(self, _path: str) -> bool:
    return self._protected


class _FakeAgent:
  """Minimal stand-in for Agent carrying just the approval plumbing."""

  def __init__(self, handler: Any, protected: bool) -> None:
    self._approval_handler = handler
    self._guardrails = {"path": _FakeGuardrail(protected)}
    self.config = Config(permissions=PermissionsConfig(filesystem_paths=(".",)))


# ---------------------------------------------------------------------------
# Diff helper
# ---------------------------------------------------------------------------


class TestGenerateDiff:
  def test_identical_content_yields_empty_diff(self) -> None:
    assert generate_diff("same\n", "same\n", "x.txt") == ""

  def test_modified_line(self) -> None:
    diff = generate_diff("a\nb\n", "a\nc\n", "x.txt")
    assert "-b" in diff
    assert "+c" in diff
    assert "x.txt (before)" in diff
    assert "x.txt (after)" in diff

  def test_new_file_shows_all_additions(self) -> None:
    diff = generate_diff("", "line1\nline2\n", "new.txt")
    assert "+line1" in diff
    assert "+line2" in diff
    assert "-line1" not in diff


# ---------------------------------------------------------------------------
# _build_approval_diff
# ---------------------------------------------------------------------------


class TestBuildApprovalDiff:
  def test_write_new_file_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    diff = _build_approval_diff("write", str(target), {"content": "all:\n\techo hi\n"})
    assert "+all:" in diff
    assert "+\techo hi" in diff

  def test_write_overwrite_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text("old:\n\techo old\n")
    diff = _build_approval_diff("write", str(target), {"content": "new:\n\techo new\n"})
    assert "-old:" in diff
    assert "+new:" in diff

  def test_update_replace_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('name = "old"\n')
    diff = _build_approval_diff(
      "update",
      str(target),
      {"operation": "replace", "old_string": "old", "new_string": "new"},
    )
    assert '-name = "old"' in diff
    assert '+name = "new"' in diff

  def test_update_delete_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('name = "x"\nextra = 1\n')
    diff = _build_approval_diff(
      "update",
      str(target),
      {"operation": "delete", "old_string": "extra = 1\n", "new_string": ""},
    )
    assert "-extra = 1" in diff

  def test_update_insert_diff_shows_insert_in_context(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("line1\nline2\nline3\n")
    diff = _build_approval_diff(
      "update",
      str(target),
      {
        "operation": "insert",
        "line_number": 2,
        "new_string": "INSERTED",
      },
    )
    # Insertion shown as an addition, surrounding lines preserved
    assert "+INSERTED" in diff
    assert "-line2" not in diff  # line2 is not removed, just shifted
    assert "line2" in diff  # line2 still appears in the diff context
    assert "line1" in diff

  def test_update_append_diff_shows_insert_in_context(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("line1\nline2\nline3\n")
    diff = _build_approval_diff(
      "update",
      str(target),
      {
        "operation": "append",
        "new_string": "APPENDED",
      },
    )
    assert "+APPENDED" in diff
    assert "-line2" not in diff
    assert "line3" in diff

  def test_update_insert_not_full_file_replacement(self, tmp_path: Path) -> None:
    """Regression: insert must not depict the whole file being replaced."""
    target = tmp_path / "pyproject.toml"
    target.write_text("line1\nline2\nline3\n")
    diff = _build_approval_diff(
      "update",
      str(target),
      {
        "operation": "insert",
        "line_number": 2,
        "new_string": "INSERTED",
      },
    )
    # The existing lines must not all appear as removed — that would
    # indicate the old buggy full-file-replacement behaviour.
    assert "-line1" not in diff
    assert "-line3" not in diff


# ---------------------------------------------------------------------------
# _maybe_block_protected — interactive approval gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_not_needed_for_non_write_tool() -> None:
  agent = _FakeAgent(handler=None, protected=True)
  result = await _maybe_block_protected(agent, "read", {"path": "/x/Makefile"})
  assert result is None


@pytest.mark.asyncio
async def test_approval_not_needed_when_no_handler_wired() -> None:
  agent = _FakeAgent(handler=None, protected=True)
  result = await _maybe_block_protected(agent, "write", {"path": "/x/Makefile", "content": "all:"})
  # No handler → simple block fallback handles it; the hook returns None.
  assert result is None


@pytest.mark.asyncio
async def test_approval_not_needed_when_path_not_protected() -> None:
  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return True

  agent = _FakeAgent(handler=handler, protected=False)
  result = await _maybe_block_protected(agent, "write", {"path": "/x/foo.txt", "content": "hi"})
  assert result is None


@pytest.mark.asyncio
async def test_approval_approved_returns_none(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"
  target.write_text("old:\n\techo old\n")

  captured: dict[str, str] = {}

  async def handler(path: str, diff: str, _kind: str = "file") -> bool:
    captured["path"] = path
    captured["diff"] = diff
    return True

  agent = _FakeAgent(handler=handler, protected=True)
  result = await _maybe_block_protected(
    agent, "write", {"path": str(target), "content": "new:\n\techo new\n"}
  )
  assert result is None  # approved → fall through to _execute_tool
  assert captured["path"] == str(target)
  assert "+new:" in captured["diff"]


@pytest.mark.asyncio
async def test_approval_denied_returns_blocked_message(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return False

  agent = _FakeAgent(handler=handler, protected=True)
  result = await _maybe_block_protected(agent, "write", {"path": str(target), "content": "new:\n"})
  assert result is not None
  message, success, raw = result
  assert success is False
  assert raw is None
  assert "denied" in message.lower()
  assert str(target) in message


@pytest.mark.asyncio
async def test_approval_handler_exception_treated_as_denial(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    raise RuntimeError("boom")

  agent = _FakeAgent(handler=handler, protected=True)
  result = await _maybe_block_protected(
    agent,
    "update",
    {"path": str(target), "operation": "replace", "old_string": "a", "new_string": "b"},
  )
  assert result is not None
  _message, success, _raw = result
  assert success is False


@pytest.mark.asyncio
async def test_namespaced_tool_name_handled(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return False

  agent = _FakeAgent(handler=handler, protected=True)
  result = await _maybe_block_protected(
    agent, "yoker:write", {"path": str(target), "content": "new:\n"}
  )
  assert result is not None
  assert result[1] is False  # denied
