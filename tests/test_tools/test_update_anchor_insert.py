"""Tests for anchor-based insert (#65) in the update tool.

Verifies the ``anchor`` + ``position`` insert mode:

1. Insert after / before a unique anchor; anchor text is preserved.
2. Multi-line anchors: 'after' inserts past the last anchor line,
   'before' inserts at the first anchor line.
3. Ambiguous anchors are rejected with match line numbers (#63 rule) —
   never first-match-silently.
4. Not-found anchors produce the closest-match error.
5. Fuzzy (whitespace-normalized) anchor matching works; fuzzy ambiguity
   is also rejected.
6. Operation inference: anchor + new_string infers 'insert'.
7. Guardrails: anchor with non-insert operation errors; invalid position
   errors; anchor takes precedence over line_number.
"""

import pytest

from yoker.builtin.update import _do_insert, update
from yoker.tools.context import ToolContext


def make_ctx() -> ToolContext:
  """Build a real ToolContext with default config (mirrors existing test helper)."""
  from yoker.config import Config

  config = Config()
  return ToolContext(
    config=config.tools.update,
    shared=config.tools_shared,
    backends={},
  )


FILE = """def alpha():
  return 1


def main():
  main()


def beta():
  return 2
"""

# ---------------------------------------------------------------------------
# Core behavior (_do_insert unit level)
# ---------------------------------------------------------------------------


class TestAnchorInsertCore:
  """Anchor positioning semantics of _do_insert."""

  def test_insert_after_single_line_anchor(self) -> None:
    content = "alpha\nbeta\ngamma\n"
    result = _do_insert(content, None, "DELTA", anchor="beta")
    assert result == "alpha\nbeta\nDELTA\ngamma\n"

  def test_insert_before_single_line_anchor(self) -> None:
    content = "alpha\nbeta\ngamma\n"
    result = _do_insert(content, None, "DELTA", anchor="beta", position="before")
    assert result == "alpha\nDELTA\nbeta\ngamma\n"

  def test_anchor_text_untouched(self) -> None:
    content = "alpha\nbeta\n"
    result = _do_insert(content, None, "DELTA", anchor="beta")
    assert "beta" in result
    assert result.index("beta") < result.index("DELTA")

  def test_insert_after_multiline_anchor(self) -> None:
    content = "A\nB\nC\nD\n"
    result = _do_insert(content, None, "X", anchor="A\nB\nC")
    assert result == "A\nB\nC\nX\nD\n"

  def test_insert_before_multiline_anchor(self) -> None:
    content = "A\nB\nC\nD\n"
    result = _do_insert(content, None, "X", anchor="B\nC", position="before")
    assert result == "A\nX\nB\nC\nD\n"

  def test_newline_added_when_missing(self) -> None:
    content = "a\nb\n"
    result = _do_insert(content, None, "no-newline", anchor="a")
    assert result == "a\nno-newline\nb\n"

  def test_anchor_not_found(self) -> None:
    with pytest.raises(ValueError, match="Search text not found"):
      _do_insert("a\nb\n", None, "X", anchor="zzz")

  def test_anchor_substring_of_line_matches(self) -> None:
    """A short anchor matching inside a line counts as a unique exact match."""
    result = _do_insert("alpha\nbeta\n", None, "X", anchor="alph")
    assert result == "alpha\nX\nbeta\n"

  def test_anchor_not_found_no_similar_line(self) -> None:
    with pytest.raises(ValueError, match="Search text not found"):
      _do_insert("alpha\nbeta\n", None, "X", anchor="zzz")

  def test_ambiguous_anchor_rejected_with_lines(self) -> None:
    content = "dup\nmid\ndup\n"
    with pytest.raises(ValueError, match="ambiguous.*line\\(s\\): 1, 3") as excinfo:
      _do_insert(content, None, "X", anchor="dup")
    assert "1, 3" in str(excinfo.value)

  def test_fuzzy_anchor_match_whitespace_normalized(self) -> None:
    content = "def  main():\n  pass\n"
    # Anchor with different whitespace still matches uniquely.
    result = _do_insert(content, None, "X", anchor="def main():")
    assert result == "def  main():\nX\n  pass\n"

  def test_fuzzy_ambiguous_anchor_rejected(self) -> None:
    # Two lines that are only fuzzy-identical (no exact match anywhere).
    content = "def  main():\n  pass\ndef   main():\n  pass\n"
    with pytest.raises(ValueError, match="[Aa]mbiguous"):
      _do_insert(content, None, "X", anchor="def main():")

  def test_exact_unique_wins_over_fuzzy_ambiguity(self) -> None:
    # Anchor exactly matches one line; a second line only fuzzy-matches.
    # Exact-unique wins, mirroring replace's exact-count semantics.
    content = "def  main():\n  pass\ndef main():\n  pass\n"
    result = _do_insert(content, None, "X", anchor="def main():")
    assert result == "def  main():\n  pass\ndef main():\nX\n  pass\n"

  def test_exact_takes_precedence_over_fuzzy(self) -> None:
    # One exact occurrence, but the text also appears inside a longer line
    # that only matches fuzzily — exact match wins.
    content = "say hi\nsay  hi again\n"
    result = _do_insert(content, None, "X", anchor="say hi")
    # Exact 'say hi' matches only once (in 'say hi\n'); the second line is
    # 'say  hi again' (double space), which fuzzy-matches but is not exact.
    assert result == "say hi\nX\nsay  hi again\n"

  def test_position_defaults_to_after(self) -> None:
    content = "a\nb\n"
    result = _do_insert(content, None, "X", anchor="a", position=None)
    assert result == "a\nX\nb\n"

  def test_insert_after_last_line_without_trailing_newline(self) -> None:
    """Live-test regression: anchor on the last line lacking a trailing
    newline — the insert must start on a fresh line, not splice mid-line."""
    content = "a\n  return 2"
    result = _do_insert(content, None, "# added", anchor="return 2")
    assert result == "a\n  return 2\n# added\n"

  def test_insert_before_anchor_with_no_leading_line_context(self) -> None:
    content = "first\nlast"
    result = _do_insert(content, None, "X", anchor="last", position="before")
    assert result == "first\nX\nlast\n"


# ---------------------------------------------------------------------------
# Tool-level integration (update())
# ---------------------------------------------------------------------------


class TestAnchorInsertTool:
  """update() integration: inference, guardrails, end-to-end."""

  @pytest.mark.asyncio
  async def test_infer_insert_from_anchor(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(str(file), make_ctx(), new_string="# hook\n", anchor="def beta():")
    assert result.success
    content = file.read_text()
    assert content.index("# hook") > content.index("def beta():")
    assert content.index("# hook") < content.index("return 2")

  @pytest.mark.asyncio
  async def test_explicit_operation_anchor_insert(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(
      str(file), make_ctx(), operation="insert", new_string="X\n", anchor="return 1"
    )
    assert result.success
    assert "return 1\nX\n" in file.read_text()

  @pytest.mark.asyncio
  async def test_anchor_before_insert(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(
      str(file), make_ctx(), new_string="# setup\n", anchor="def main():", position="before"
    )
    assert result.success
    content = file.read_text()
    assert content.index("# setup") < content.index("def main():")

  @pytest.mark.asyncio
  async def test_ambiguous_anchor_fails_loud(self, tmp_path) -> None:
    file2 = tmp_path / "g.py"
    file2.write_text("x = main()\ny = main()\n")
    result2 = await update(str(file2), make_ctx(), new_string="X\n", anchor="main()")
    assert not result2.success
    assert "ambiguous" in result2.error.lower()
    assert "1, 2" in result2.error

  @pytest.mark.asyncio
  async def test_anchor_with_wrong_operation_errors(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(
      str(file), make_ctx(), operation="replace", new_string="X", anchor="return 1"
    )
    assert not result.success
    assert "anchor is only valid for operation='insert'" in result.error

  @pytest.mark.asyncio
  async def test_invalid_position_errors(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(
      str(file),
      make_ctx(),
      operation="insert",
      new_string="X",
      anchor="return 1",
      position="beside",
    )
    assert not result.success
    assert "Invalid position" in result.error

  @pytest.mark.asyncio
  async def test_anchor_takes_precedence_over_line_number(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    # line_number=1 would insert at the top; anchor wins.
    result = await update(
      str(file),
      make_ctx(),
      operation="insert",
      new_string="X\n",
      anchor="return 2",
      line_number=1,
    )
    assert result.success
    content = file.read_text()
    assert content.index("X") > content.index("return 2")
    assert not content.startswith("X")

  @pytest.mark.asyncio
  async def test_insert_without_anchor_or_line_number_unchanged(self, tmp_path) -> None:
    """Regression: line-based insert without line_number still errors clearly."""
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(str(file), make_ctx(), operation="insert", new_string="X")
    assert not result.success
    assert "line_number is required for insert operations" in result.error

  @pytest.mark.asyncio
  async def test_inferred_anchor_insert_advises_explicit(self, tmp_path) -> None:
    file = tmp_path / "f.py"
    file.write_text(FILE)
    result = await update(str(file), make_ctx(), new_string="X\n", anchor="return 1")
    assert result.success
    assert "operation inferred: 'insert'" in result.result


# ---------------------------------------------------------------------------
# Live-validated edge cases pinned as unit tests
# ---------------------------------------------------------------------------


class TestAnchorInsertLiveParity:
  """Pin behaviors that were live-validated in dogfooding but were not yet
  covered by unit tests."""

  def test_not_found_anchor_includes_closest_match_hint(self) -> None:
    """Anchor with no (even fuzzy) match gets the closest-match context."""
    with pytest.raises(ValueError, match="Closest match at line") as excinfo:
      _do_insert("alpha\nbeta\n", None, "X", anchor="alphz")
    assert "alpha" in str(excinfo.value)

  def test_insert_before_first_line_top_of_file(self) -> None:
    """'before' on the file's first line inserts at the very top."""
    result = _do_insert(
      "import os\nx = 1\n", None, "# header", anchor="import os", position="before"
    )
    assert result == "# header\nimport os\nx = 1\n"

  def test_regex_special_chars_in_anchor_exact(self) -> None:
    """Quotes, braces and colons in the anchor are matched literally."""
    content = 'config = {"retries": 3}\n'
    result = _do_insert(content, None, "# done", anchor='config = {"retries": 3}')
    assert result == 'config = {"retries": 3}\n# done\n'

  def test_regex_special_chars_in_anchor_fuzzy(self) -> None:
    """Whitespace-variant of a special-char anchor matches via fuzzy path."""
    content = 'config = {"retries": 3}\n'
    result = _do_insert(content, None, "# done", anchor='"retries":  3}')
    assert result == 'config = {"retries": 3}\n# done\n'

  def test_multiline_exact_run_ambiguity_rejected(self) -> None:
    """A repeated multi-line anchor is rejected with both run positions."""
    content = "step()\nlog()\nmid\nstep()\nlog()\n"
    with pytest.raises(ValueError, match="ambiguous") as excinfo:
      _do_insert(content, None, "X", anchor="step()\nlog()")
    assert "1, 4" in str(excinfo.value)

  def test_context_lines_disambiguate_multiline_anchor(self) -> None:
    """Adding unique context lines to the anchor resolves the ambiguity."""
    content = "step()\nlog()\nmid\nstep()\nlog()\n"
    result = _do_insert(content, None, "# tail", anchor="mid\nstep()\nlog()")
    assert result == "step()\nlog()\nmid\nstep()\nlog()\n# tail\n"

  def test_blank_new_string_inserts_single_newline(self) -> None:
    """Empty new_string is a valid pure-spacing insert (one blank line)."""
    result = _do_insert("alpha\nbeta\n", None, "", anchor="alpha")
    assert result == "alpha\n\nbeta\n"

  @pytest.mark.asyncio
  async def test_anchor_with_delete_operation_errors(self, tmp_path) -> None:
    """Guardrail also fires for the delete operation (not just replace)."""
    file = tmp_path / "f.py"
    file.write_text("a\nb\n")
    result = await update(str(file), make_ctx(), operation="delete", new_string="X", anchor="a")
    assert not result.success
    assert "anchor is only valid for operation='insert'" in result.error
