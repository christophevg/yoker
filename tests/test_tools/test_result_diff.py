"""Tests for LLM-facing result diffs (#62) in the update and write tools.

Verifies that successful edits return a compact diff of the applied change
in the result string — stats always present, diff body capped at 60 lines —
so the model can verify the change without a read-after-write round trip.

- update: all operations append (stat + diff) to the result message.
- write: new files get stat-only; overwrites get stat + diff.
- Truncation: >60 diff lines are summarized, stats preserved.
- content_metadata (the UI channel) is unaffected.
"""

import pytest

from yoker.builtin.update import _append_result_diff, update
from yoker.builtin.write import _build_write_result_message, write
from yoker.tools.context import ToolContext


def make_ctx() -> ToolContext:
  """Build a real ToolContext with default config."""
  from yoker.config import Config

  config = Config()
  return ToolContext(
    config=config.tools.update,
    shared=config.tools_shared,
    backends={},
  )


def make_write_ctx() -> ToolContext:
  """Build a ToolContext with allow_overwrite enabled for write tests."""
  from yoker.config import Config, ToolsConfig, WriteToolConfig

  config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
  return ToolContext(
    config=config.tools.write,
    shared=config.tools_shared,
    backends={},
  )


# ---------------------------------------------------------------------------
# _append_result_diff unit level (update)
# ---------------------------------------------------------------------------


class TestAppendResultDiff:
  """Diff formatting in the update result string."""

  def test_small_change_stat_and_full_diff(self) -> None:
    old = "a\nb\nc\n"
    new = "a\nB\nc\n"
    result = _append_result_diff("File updated successfully", old, new, "f.txt")
    assert result.startswith("File updated successfully (+1 \u22121)")
    assert "\n-b\n" in result
    assert "\n+B\n" in result

  def test_stat_counts_additions_and_removals(self) -> None:
    old = "one\ntwo\nthree\n"
    new = "one\nTWO\nTHREE\nfour\n"
    result = _append_result_diff("Done", old, new, "f.txt")
    # difflib emits -two -three +TWO +THREE +four (block replacement).
    assert result.startswith("Done (+3 \u22122)")

  def test_no_content_change(self) -> None:
    result = _append_result_diff("File updated successfully", "same\n", "same\n", "f.txt")
    assert result == "File updated successfully (no content change)"

  def test_truncated_diff_preserves_stat(self) -> None:
    old = "".join(f"line{i}\n" for i in range(100))
    new = "".join(f"LINE{i}\n" for i in range(100))
    result = _append_result_diff("Done", old, new, "f.txt")
    assert result.startswith("Done (+100 \u2212100)")
    assert "... 143 more diff lines" in result
    # First diff line present (header preserved by line order).
    assert "---" in result

  def test_truncation_cap_is_60_lines(self) -> None:
    old = "".join(f"line{i}\n" for i in range(100))
    new = "".join(f"LINE{i}\n" for i in range(100))
    result = _append_result_diff("Done", old, new, "f.txt")
    diff_body_lines = [
      line
      for line in result.splitlines()
      if line.startswith(("+", "-", "@")) and not line.startswith("... ")
    ]
    assert len(diff_body_lines) <= 60

  def test_message_with_inference_advice_kept(self) -> None:
    msg = "File updated successfully (operation inferred: 'replace'). Next time, ..."
    result = _append_result_diff(msg, "a\n", "b\n", "f.txt")
    assert result.startswith(msg.split(".")[0])


# ---------------------------------------------------------------------------
# update() integration
# ---------------------------------------------------------------------------


class TestUpdateResultDiff:
  """update() returns the applied diff in the result string."""

  @pytest.mark.asyncio
  async def test_replace_result_includes_diff(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text("alpha\nbeta\ngamma\n")
    result = await update(
      str(file), make_ctx(), operation="replace", old_string="beta", new_string="BETA"
    )
    assert result.success
    assert result.result.startswith("File updated successfully (+1 \u22121)")
    assert "-beta" in result.result
    assert "+BETA" in result.result

  @pytest.mark.asyncio
  async def test_insert_result_includes_diff(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text("a\nb\n")
    result = await update(str(file), make_ctx(), operation="insert", line_number=2, new_string="X")
    assert result.success
    assert result.result.startswith("File updated successfully (+1 \u22120)")
    assert "+X" in result.result

  @pytest.mark.asyncio
  async def test_anchor_insert_result_includes_diff(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text("a\nb\n")
    result = await update(str(file), make_ctx(), new_string="X", anchor="a")
    assert result.success
    assert "+X" in result.result

  @pytest.mark.asyncio
  async def test_delete_result_includes_diff(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text("a\nb\nc\n")
    result = await update(str(file), make_ctx(), operation="delete", old_string="b\n")
    assert result.success
    assert result.result.startswith("File updated successfully (+0 \u22121)")

  @pytest.mark.asyncio
  async def test_content_metadata_unaffected(self, tmp_path) -> None:
    """The UI channel (content_metadata) still works alongside the diff."""
    file = tmp_path / "f.py"
    file.write_text("alpha\nbeta\n")
    result = await update(
      str(file), make_ctx(), operation="replace", old_string="beta", new_string="BETA"
    )
    assert result.success
    assert result.content_metadata is not None
    assert "operation" in result.content_metadata


# ---------------------------------------------------------------------------
# write() result message
# ---------------------------------------------------------------------------


class TestWriteResultDiff:
  """write(): stat for new files, stat + diff for overwrites."""

  @pytest.mark.asyncio
  async def test_new_file_stat_only(self, tmp_path) -> None:
    file = tmp_path / "new.txt"
    result = await write(str(file), "one\ntwo\n", make_write_ctx())
    assert result.success
    assert result.result == "File written successfully (2 lines, 8 bytes)"
    assert "-" not in result.result.split("\n", 1)[1] if "\n" in result.result else True

  @pytest.mark.asyncio
  async def test_overwrite_includes_diff(self, tmp_path) -> None:
    file = tmp_path / "over.txt"
    file.write_text("old1\nold2\n")
    result = await write(str(file), "old1\nnew2\n", make_write_ctx())
    assert result.success
    assert "File written successfully (2 lines, 10 bytes) (+1 \u22121)" in result.result
    assert "\n-old2" in result.result
    assert "\n+new2" in result.result

  @pytest.mark.asyncio
  async def test_overwrite_identical_content_no_change(self, tmp_path) -> None:
    file = tmp_path / "same.txt"
    file.write_text("same\n")
    result = await write(str(file), "same\n", make_write_ctx())
    assert result.success
    assert result.result == "File written successfully (1 lines, 5 bytes) (no content change)"

  def test_build_message_new_file(self) -> None:
    from pathlib import Path as P

    msg = _build_write_result_message("hello\n", False, None, P("/tmp/x.txt"))
    assert msg == "File written successfully (1 lines, 6 bytes)"

  def test_build_message_binary_undecodable_previous(self) -> None:
    """Previous content that failed to decode (None) degrades to stat-only."""
    from pathlib import Path as P

    msg = _build_write_result_message("data\n", True, None, P("/tmp/x.txt"))
    assert msg == "File written successfully (1 lines, 5 bytes)"

  @pytest.mark.asyncio
  async def test_large_overwrite_truncated(self, tmp_path) -> None:
    file = tmp_path / "big.txt"
    file.write_text("".join(f"old{i}\n" for i in range(100)))
    result = await write(str(file), "".join(f"NEW{i}\n" for i in range(100)), make_write_ctx())
    assert result.success
    assert "... 143 more diff lines" in result.result
