"""Tests for update tool improvements: line_range, fuzzy matching, error messages."""

from pathlib import Path

import pytest

from yoker.builtin import update
from yoker.config import Config
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext


def _update_spec():
  """Create and register the update tool."""
  registry = ToolRegistry()
  return registry.register(update, name="update")


def _update_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for update tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.update,
    shared=config.tools_shared,
    backends={},
  )


class TestLineRangeReplace:
  """Test line_range-based replace operation."""

  @pytest.mark.asyncio
  async def test_replace_single_line_by_range(self, tmp_path: Path) -> None:
    """
    Given: a file with multiple lines
    When: replace with line_range=[2, 2]
    Then: only line 2 is replaced with new_string
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="Replaced Line 2",
      line_range=[2, 2],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nReplaced Line 2\nLine 3\n"

  @pytest.mark.asyncio
  async def test_replace_multiple_lines_by_range(self, tmp_path: Path) -> None:
    """
    Given: a file with multiple lines
    When: replace with line_range=[2, 4]
    Then: lines 2-4 are replaced with new_string
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="Replaced\nMultiple\nLines",
      line_range=[2, 4],
      ctx=ctx,
    )

    assert result.success
    expected = "Line 1\nReplaced\nMultiple\nLines\nLine 5\n"
    assert test_file.read_text() == expected

  @pytest.mark.asyncio
  async def test_replace_range_at_end_of_file(self, tmp_path: Path) -> None:
    """
    Given: a file with 3 lines
    When: replace with line_range=[2, 10] (end exceeds file)
    Then: replaces from line 2 to end of file (clamped)
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="End content",
      line_range=[2, 10],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nEnd content\n"

  @pytest.mark.asyncio
  async def test_replace_range_without_trailing_newline(self, tmp_path: Path) -> None:
    """
    Given: a file without trailing newline
    When: replace with line_range covering the last line
    Then: a newline is added to the replacement
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3")  # no trailing \n

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="New last line",
      line_range=[3, 3],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nLine 2\nNew last line\n"

  @pytest.mark.asyncio
  async def test_replace_range_invalid_start(self, tmp_path: Path) -> None:
    """
    Given: a file with 3 lines
    When: replace with line_range=[0, 2] (start < 1)
    Then: error about start being >= 1
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="X",
      line_range=[0, 2],
      ctx=ctx,
    )

    assert not result.success
    assert "must be >= 1" in result.error

  @pytest.mark.asyncio
  async def test_replace_range_end_before_start(self, tmp_path: Path) -> None:
    """
    Given: a file with 3 lines
    When: replace with line_range=[3, 1] (end < start)
    Then: error about end being >= start
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="X",
      line_range=[3, 1],
      ctx=ctx,
    )

    assert not result.success
    assert "must be >= start" in result.error

  @pytest.mark.asyncio
  async def test_replace_range_start_beyond_file(self, tmp_path: Path) -> None:
    """
    Given: a file with 3 lines
    When: replace with line_range=[10, 15] (start > total)
    Then: error about start being out of range
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="X",
      line_range=[10, 15],
      ctx=ctx,
    )

    assert not result.success
    assert "out of range" in result.error

  @pytest.mark.asyncio
  async def test_replace_empty_file_by_range(self, tmp_path: Path) -> None:
    """
    Given: an empty file
    When: replace with line_range=[1, 1]
    Then: error about file having 0 lines
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      new_string="Content",
      line_range=[1, 1],
      ctx=ctx,
    )

    assert not result.success
    assert "0 lines" in result.error

  @pytest.mark.asyncio
  async def test_replace_range_takes_precedence_over_old_string(self, tmp_path: Path) -> None:
    """
    Given: a file with content
    When: replace with both old_string and line_range
    Then: line_range takes precedence
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="This should be ignored",
      new_string="Line-based replacement",
      line_range=[2, 2],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nLine-based replacement\nLine 3\n"


class TestLineRangeDelete:
  """Test line_range-based delete operation."""

  @pytest.mark.asyncio
  async def test_delete_single_line_by_range(self, tmp_path: Path) -> None:
    """
    Given: a file with 3 lines
    When: delete with line_range=[2, 2]
    Then: line 2 is removed
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="delete",
      line_range=[2, 2],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nLine 3\n"

  @pytest.mark.asyncio
  async def test_delete_multiple_lines_by_range(self, tmp_path: Path) -> None:
    """
    Given: a file with 5 lines
    When: delete with line_range=[2, 4]
    Then: lines 2-4 are removed
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")

    result = await spec.execute(
      path=str(test_file),
      operation="delete",
      line_range=[2, 4],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nLine 5\n"

  @pytest.mark.asyncio
  async def test_delete_range_at_end_clamped(self, tmp_path: Path) -> None:
    """
    Given: a file with 3 lines
    When: delete with line_range=[2, 100]
    Then: deletes from line 2 to end (clamped)
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="delete",
      line_range=[2, 100],
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\n"


class TestFuzzyMatching:
  """Test whitespace-insensitive matching via require_exact_match=False."""

  @pytest.mark.asyncio
  async def test_fuzzy_replace_extra_whitespace(self, tmp_path: Path) -> None:
    """
    Given: a file with extra spaces in content
    When: replace with require_exact_match=False and old_string with single spaces
    Then: the match is found despite whitespace differences
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("def   foo(  x,  y  ):\n  return x\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="def foo( x, y ):",
      new_string="def bar( x, y ):",
      require_exact_match=False,
      ctx=ctx,
    )

    assert result.success
    content = test_file.read_text()
    # Fuzzy replace swaps the entire matched region with new_string
    assert "def bar( x, y ):" in content
    assert "foo" not in content

  @pytest.mark.asyncio
  async def test_fuzzy_replace_exact_still_works(self, tmp_path: Path) -> None:
    """
    Given: a file with exact match available
    When: replace with require_exact_match=False
    Then: exact match is found (fuzzy is a superset)
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="Line 2",
      new_string="Replaced",
      require_exact_match=False,
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nReplaced\nLine 3\n"

  @pytest.mark.asyncio
  async def test_fuzzy_delete_with_whitespace(self, tmp_path: Path) -> None:
    """
    Given: a file with extra whitespace
    When: delete with require_exact_match=False
    Then: the fuzzy match is found and deleted
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\n  remove   me  \nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="delete",
      old_string="remove me",
      require_exact_match=False,
      ctx=ctx,
    )

    assert result.success
    content = test_file.read_text()
    assert "remove" not in content


class TestPerCallExactMatchOverride:
  """Test require_exact_match per-call override."""

  @pytest.mark.asyncio
  async def test_override_to_false_allows_multiple_matches(self, tmp_path: Path) -> None:
    """
    Given: a file with multiple occurrences of old_string
    When: replace with require_exact_match=False
    Then: first match is replaced (no ambiguity error)
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("todo: fix this\ntodo: fix that\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="todo:",
      new_string="done:",
      require_exact_match=False,
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "done: fix this\ntodo: fix that\n"

  @pytest.mark.asyncio
  async def test_override_to_true_blocks_multiple_matches(self, tmp_path: Path) -> None:
    """
    Given: config default is require_exact_match=False, but per-call override=True
    When: replace with multiple matches
    Then: ambiguity error is raised
    """
    config = Config()
    config.tools.update.require_exact_match = False
    spec = _update_spec()
    ctx = _update_context(config)
    test_file = tmp_path / "test.txt"
    test_file.write_text("todo: fix this\ntodo: fix that\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="todo:",
      new_string="done:",
      require_exact_match=True,
      ctx=ctx,
    )

    assert not result.success
    assert "multiple times" in result.error


class TestBetterErrorMessages:
  """Test improved error messages with closest match and line numbers."""

  @pytest.mark.asyncio
  async def test_not_found_includes_closest_match(self, tmp_path: Path) -> None:
    """
    Given: a file with similar content
    When: replace with old_string that doesn't match exactly
    Then: error message includes closest match with similarity percentage
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("def hello_world():\n  return 42\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="def hello_word():",
      new_string="def goodbye():",
      ctx=ctx,
    )

    assert not result.success
    assert "Search text not found" in result.error
    assert "Closest match" in result.error
    assert "similarity" in result.error

  @pytest.mark.asyncio
  async def test_multiple_matches_includes_line_numbers(self, tmp_path: Path) -> None:
    """
    Given: a file with old_string appearing multiple times
    When: replace with require_exact_match=True
    Then: error message includes line numbers of matches
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("import os\nimport sys\nimport os\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="import os",
      new_string="import pathlib",
      ctx=ctx,
    )

    assert not result.success
    assert "multiple times" in result.error
    assert "line" in result.error.lower()
    assert "line_range" in result.error

  @pytest.mark.asyncio
  async def test_not_found_no_close_match(self, tmp_path: Path) -> None:
    """
    Given: a file with completely different content
    When: replace with old_string that has no close match
    Then: error message says 'Search text not found' without closest match info
    """
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="zzzzzzzzzz completely different",
      new_string="X",
      ctx=ctx,
    )

    assert not result.success
    assert "Search text not found" in result.error


class TestExistingBehaviorPreserved:
  """Test that existing behavior (old_string-based replace/delete) is preserved."""

  @pytest.mark.asyncio
  async def test_string_replace_still_works(self, tmp_path: Path) -> None:
    """Basic string replace still works without line_range."""
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nOld\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old",
      new_string="New",
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nNew\nLine 3\n"

  @pytest.mark.asyncio
  async def test_string_delete_still_works(self, tmp_path: Path) -> None:
    """Basic string delete still works without line_range."""
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nDelete me\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="delete",
      old_string="Delete me\n",
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nLine 3\n"

  @pytest.mark.asyncio
  async def test_line_number_delete_still_works(self, tmp_path: Path) -> None:
    """Line-number-based delete still works."""
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    result = await spec.execute(
      path=str(test_file),
      operation="delete",
      line_number=2,
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nLine 3\n"

  @pytest.mark.asyncio
  async def test_insert_before_still_works(self, tmp_path: Path) -> None:
    """Insert before still works."""
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\n")

    result = await spec.execute(
      path=str(test_file),
      operation="insert_before",
      line_number=2,
      new_string="Inserted",
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nInserted\nLine 2\n"

  @pytest.mark.asyncio
  async def test_insert_after_still_works(self, tmp_path: Path) -> None:
    """Insert after still works."""
    spec = _update_spec()
    ctx = _update_context()
    test_file = tmp_path / "test.txt"
    test_file.write_text("Line 1\nLine 2\n")

    result = await spec.execute(
      path=str(test_file),
      operation="insert_after",
      line_number=1,
      new_string="Inserted",
      ctx=ctx,
    )

    assert result.success
    assert test_file.read_text() == "Line 1\nInserted\nLine 2\n"
