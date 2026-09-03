"""Tests for the protected-file interactive approval flow (MBI-009 T12).

Covers the processing-loop approval hook in :mod:`yoker.core._processing`
and the diff helper in :mod:`yoker.tools.diff`. The WritePathGuardrail simple
block is covered in ``tests/tools/test_path_guardrail_protected.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest

from yoker.builtin import file as file_tool
from yoker.builtin import write as write_tool
from yoker.builtin.file import _approval_prompt as file_prompt
from yoker.builtin.git import _approval_prompt as git_prompt
from yoker.builtin.update import _approval_prompt as update_prompt
from yoker.builtin.write import _approval_prompt as write_prompt
from yoker.config import Config, PermissionsConfig
from yoker.core._processing import _maybe_approve_write_blocked
from yoker.tools.annotations import ReadPath, Text
from yoker.tools.annotations import WritePath as PathArg
from yoker.tools.diff import generate_diff
from yoker.tools.schema import ToolSpec, build_tool_spec


class _FakeGuardrail:
  """Minimal stand-in for WritePathGuardrail exposing is_write_blocked + scope checks."""

  def __init__(self, protected: bool) -> None:
    self._protected = protected

  def is_write_blocked(self, _path: str) -> bool:
    return self._protected

  def _resolve_path(self, path_str: str) -> Any:
    import os
    from pathlib import Path

    try:
      return Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      return None

  def _is_within_allowed_paths(self, _resolved: Any) -> bool:
    # Tests use paths within "." — always allow in the fake.
    return True


class _FakeAgent:
  """Minimal stand-in for Agent carrying just the approval plumbing."""

  def __init__(self, handler: Any, protected: bool) -> None:
    self._approval_handler = handler
    self._guardrails = {"path_write": _FakeGuardrail(protected)}
    self.config = Config(permissions=PermissionsConfig(filesystem_paths=(".",)))


# ---------------------------------------------------------------------------
# Helpers to build ToolSpecs for tests
# ---------------------------------------------------------------------------


async def _dummy_write(
  path: Annotated[str, PathArg("Path to the file to write")],
  content: Annotated[str, Text("Content to write")],
  ctx: Any = None,
  create_parents: bool = False,
) -> Any:
  """Write content to a file."""
  ...


async def _dummy_update(
  path: Annotated[str, PathArg("Path to the file to update")],
  ctx: Any = None,
  operation: Annotated[str, Text("File operation")] = "replace",
  old_string: Annotated[str, Text("Text to find")] = "",
  new_string: Annotated[str, Text("Replacement text")] = "",
  line_number: Any = None,
  line_range: Any = None,
  require_exact_match: Any = None,
) -> Any:
  """Update an existing file."""
  ...


async def _dummy_read(
  path: Annotated[str, ReadPath("Path to the file to read")],
  ctx: Any = None,
  offset: int = 0,
  limit: int = 0,
) -> Any:
  """Read file contents."""
  ...


async def _dummy_file(
  operation: Annotated[str, Text("File operation")],
  source: Annotated[str, PathArg("Source file path")],
  destination: Annotated[str, PathArg("Destination file path")] = "",
  ctx: Any = None,
  recursive: bool = False,
) -> Any:
  """Execute a file operation (copy, move, delete)."""
  ...


def _make_spec(tool_callable: Any, simple_name: str, namespace: str = "yoker") -> ToolSpec:
  """Build a namespaced ToolSpec like the plugin loader does."""
  return build_tool_spec(tool_callable, namespace=namespace, name=simple_name)


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
# Tool approval-prompt providers (yoker.builtin.write / update / file / git)
# ---------------------------------------------------------------------------


class TestWriteApprovalPrompt:
  """The write tool's own provider builds the same diff core used to build."""

  def test_write_new_file_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    prompt = write_prompt({"path": str(target), "content": "all:\n\techo hi\n"})
    assert prompt.label == str(target)
    assert prompt.kind == "file"
    assert "+all:" in prompt.preview
    assert "+\techo hi" in prompt.preview

  def test_write_overwrite_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text("old:\n\techo old\n")
    prompt = write_prompt({"path": str(target), "content": "new:\n\techo new\n"})
    assert "-old:" in prompt.preview
    assert "+new:" in prompt.preview

  def test_unreadable_file_yields_all_additions_diff(self, tmp_path: Path) -> None:
    prompt = write_prompt({"path": str(tmp_path / "missing.txt"), "content": "x\n"})
    assert "+x" in prompt.preview


class TestUpdateApprovalPrompt:
  def test_update_replace_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('name = "old"\n')
    prompt = update_prompt(
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"}
    )
    assert '-name = "old"' in prompt.preview
    assert '+name = "new"' in prompt.preview

  def test_update_delete_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('name = "x"\nextra = 1\n')
    prompt = update_prompt(
      {"path": str(target), "operation": "delete", "old_string": "extra = 1\n", "new_string": ""}
    )
    assert "-extra = 1" in prompt.preview

  def test_update_insert_diff_shows_insert_in_context(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("line1\nline2\nline3\n")
    prompt = update_prompt(
      {
        "path": str(target),
        "operation": "insert",
        "line_number": 2,
        "new_string": "INSERTED",
      }
    )
    # Insertion shown as an addition, surrounding lines preserved
    assert "+INSERTED" in prompt.preview
    assert "-line2" not in prompt.preview  # line2 is not removed, just shifted
    assert "line2" in prompt.preview  # line2 still appears in the diff context
    assert "line1" in prompt.preview

  def test_update_append_diff_shows_insert_in_context(self, tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text("line1\nline2\nline3\n")
    prompt = update_prompt(
      {
        "path": str(target),
        "operation": "append",
        "new_string": "APPENDED",
      }
    )
    assert "+APPENDED" in prompt.preview
    assert "-line2" not in prompt.preview
    assert "line3" in prompt.preview

  def test_update_insert_not_full_file_replacement(self, tmp_path: Path) -> None:
    """Regression: insert must not depict the whole file being replaced."""
    target = tmp_path / "pyproject.toml"
    target.write_text("line1\nline2\nline3\n")
    prompt = update_prompt(
      {
        "path": str(target),
        "operation": "insert",
        "line_number": 2,
        "new_string": "INSERTED",
      }
    )
    # The existing lines must not all appear as removed — that would
    # indicate the old buggy full-file-replacement behaviour.
    assert "-line1" not in prompt.preview
    assert "-line3" not in prompt.preview


class TestFileApprovalPrompt:
  def test_file_delete_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text("all:\n\techo hi\n")
    prompt = file_prompt({"operation": "delete", "source": str(target)})
    assert "-all:" in prompt.preview
    assert "-\techo hi" in prompt.preview

  def test_file_move_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    prompt = file_prompt(
      {"operation": "move", "source": str(target), "destination": "/elsewhere/Makefile.bak"}
    )
    assert "move" in prompt.preview.lower()
    assert str(target) in prompt.preview

  def test_file_copy_diff(self, tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    prompt = file_prompt(
      {"operation": "copy", "source": str(target), "destination": "/elsewhere/Makefile.bak"}
    )
    assert "copy" in prompt.preview.lower()


class TestGitApprovalPrompt:
  """The git provider names the actual operation — no fabricated file diff."""

  def test_diff_operation_honest_prompt(self) -> None:
    prompt = git_prompt({"operation": "diff", "path": "Makefile"})
    assert prompt.label == "git diff"
    assert prompt.kind == "git"
    assert "Makefile" in prompt.preview
    assert "(approved)" not in prompt.preview
    # No fabricated modification: the preview must not look like a diff
    # body changing the file.
    assert not prompt.preview.startswith("-")
    assert " (approved)" not in prompt.preview

  def test_commit_operation(self) -> None:
    prompt = git_prompt({"operation": "commit", "path": "."})
    assert prompt.label == "git commit"
    assert prompt.kind == "git"
    assert "write-protected" in prompt.preview

  def test_operation_missing_label_still_safe(self) -> None:
    prompt = git_prompt({})
    assert prompt.label == "git"
    assert prompt.kind == "git"


# ---------------------------------------------------------------------------
# _maybe_approve_write_blocked — interactive approval gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_not_needed_for_non_write_tool() -> None:
  agent = _FakeAgent(handler=None, protected=True)
  spec = _make_spec(_dummy_read, "read")
  result = await _maybe_approve_write_blocked(agent, spec, {"path": "/x/Makefile"})
  assert result is False


@pytest.mark.asyncio
async def test_read_never_triggers_approval_even_with_handler() -> None:
  """Read on a write-blocked path must NOT trigger the approval flow.

  The guardrail never blocks reads, so the approval
  hook must not fire for read-only tools (read, list, search, existence).
  """

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    raise AssertionError("Approval handler should not be called for read")

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(_dummy_read, "read")
  result = await _maybe_approve_write_blocked(agent, spec, {"path": "/x/Makefile"})
  assert result is False


@pytest.mark.asyncio
async def test_approval_not_needed_when_no_handler_wired() -> None:
  agent = _FakeAgent(handler=None, protected=True)
  spec = _make_spec(_dummy_write, "write")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"path": "/x/Makefile", "content": "all:"}
  )
  # No handler → guardrail handles it; the hook returns False.
  assert result is False


@pytest.mark.asyncio
async def test_approval_not_needed_when_path_not_protected() -> None:
  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return True

  agent = _FakeAgent(handler=handler, protected=False)
  spec = _make_spec(_dummy_write, "write")
  result = await _maybe_approve_write_blocked(agent, spec, {"path": "/x/foo.txt", "content": "hi"})
  assert result is False


@pytest.mark.asyncio
async def test_approval_approved_returns_true(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"
  target.write_text("old:\n\techo old\n")

  captured: dict[str, str] = {}

  async def handler(path: str, diff: str, _kind: str = "file") -> bool:
    captured["path"] = path
    captured["diff"] = diff
    return True

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(write_tool, "write")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"path": str(target), "content": "new:\n\techo new\n"}
  )
  assert result is True  # approved → skip guardrail blocked_write_paths
  assert captured["path"] == str(target)
  assert "+new:" in captured["diff"]


@pytest.mark.asyncio
async def test_generic_default_prompt_for_tool_without_provider(tmp_path: Path) -> None:
  """A tool without ``__yoker_approval__`` gets the honest generic prompt.

  No fabricated diff — just the tool name, the protected path, and what
  approval means. This is the default every new tool inherits.
  """
  target = tmp_path / "Makefile"

  captured: dict[str, str] = {}

  async def handler(path: str, preview: str, kind: str = "file") -> bool:
    captured["path"] = path
    captured["preview"] = preview
    captured["kind"] = kind
    return True

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(_dummy_write, "write")  # dummy has no __yoker_approval__
  result = await _maybe_approve_write_blocked(
    agent, spec, {"path": str(target), "content": "anything"}
  )
  assert result is True
  assert captured["path"] == str(target)
  assert captured["kind"] == "file"
  assert "'write'" in captured["preview"]
  assert "write-protected" in captured["preview"]
  assert "(approved)" not in captured["preview"]
  assert "+new:" not in captured["preview"]  # no fabricated diff


@pytest.mark.asyncio
async def test_approval_denied_returns_false(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return False

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(_dummy_write, "write")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"path": str(target), "content": "new:\n"}
  )
  assert result is False  # denied → guardrail will block


@pytest.mark.asyncio
async def test_approval_handler_exception_treated_as_denial(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    raise RuntimeError("boom")

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(_dummy_update, "update")
  result = await _maybe_approve_write_blocked(
    agent,
    spec,
    {"path": str(target), "operation": "replace", "old_string": "a", "new_string": "b"},
  )
  assert result is False  # exception → denial


@pytest.mark.asyncio
async def test_namespaced_tool_name_handled(tmp_path: Path) -> None:
  target = tmp_path / "Makefile"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return False

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(_dummy_write, "write")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"path": str(target), "content": "new:\n"}
  )
  assert result is False  # denied


# ---------------------------------------------------------------------------
# _maybe_approve_write_blocked — file tool (source/destination params)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_file_tool_delete_protected(tmp_path: Path) -> None:
  """The file tool with a write-blocked source must trigger the approval flow."""
  target = tmp_path / "Makefile"
  target.write_text("all:\n\techo hi\n")

  captured: dict[str, str] = {}

  async def handler(path: str, diff: str, _kind: str = "file") -> bool:
    captured["path"] = path
    captured["diff"] = diff
    return True

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(file_tool, "file")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"operation": "delete", "source": str(target)}
  )
  assert result is True
  assert captured["path"] == str(target)
  assert "-all:" in captured["diff"]  # delete shows content being removed


@pytest.mark.asyncio
async def test_approval_file_tool_move_protected(tmp_path: Path) -> None:
  """The file tool moving a write-blocked file must trigger approval."""
  target = tmp_path / "Makefile"
  dest = tmp_path / "Makefile.bak"

  async def handler(_path: str, _diff: str, _kind: str = "file") -> bool:
    return False

  agent = _FakeAgent(handler=handler, protected=True)
  spec = _make_spec(_dummy_file, "file")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"operation": "move", "source": str(target), "destination": str(dest)}
  )
  assert result is False  # denied


@pytest.mark.asyncio
async def test_approval_file_tool_no_handler_returns_false(tmp_path: Path) -> None:
  """Without a handler, the file tool approval returns False (guardrail blocks)."""
  target = tmp_path / "Makefile"

  agent = _FakeAgent(handler=None, protected=True)
  spec = _make_spec(_dummy_file, "file")
  result = await _maybe_approve_write_blocked(
    agent, spec, {"operation": "delete", "source": str(target)}
  )
  assert result is False
