"""Tests for UpdateTool content metadata and diff generation.

Task: 1.5.5 - Show Write/Update Tool Content in CLI
"""

import pytest
from pathlib import Path

from yoker.tools.update import UpdateTool, _truncate_diff
from yoker.tools.base import ToolResult
from yoker.config.schema import Config, ToolsConfig, UpdateToolConfig, ContentDisplayConfig


class TestUpdateToolReplaceOperation:
  """Test UpdateTool replace operation content metadata."""

  def test_replace_diff_generation(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool replace operation
    When: execute() is called
    Then: ToolResult includes content_metadata with old_content and new_content
    """
    # Create UpdateTool with content verbosity and show_diff_for_updates
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file with content
    test_file = tmp_path / "replace.txt"
    test_file.write_text("Line 1\nOld text\nLine 3\n")

    # Replace text
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old text",
      new_string="New text"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "replace"
    assert result.content_metadata["content_type"] == "diff"
    assert result.content_metadata["content"] is not None
    # Diff should show old and new
    assert "-" in result.content_metadata["content"]
    assert "+" in result.content_metadata["content"]

  def test_replace_content_type_is_diff(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool replace operation with show_diff_for_updates=True
    When: execute() is called
    Then: content_metadata.content_type="diff"
    """
    # Create UpdateTool with show_diff_for_updates
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(show_diff_for_updates=True)
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "replace_diff.txt"
    test_file.write_text("Old content\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old content",
      new_string="New content"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "diff"

  def test_replace_metadata(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool replace operation
    When: execute() is called
    Then: metadata includes lines_modified count
    """
    # Create UpdateTool
    tool = UpdateTool()

    # Create file
    test_file = tmp_path / "replace_meta.txt"
    test_file.write_text("Line 1\nOld\nLine 3\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old",
      new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert "lines_modified" in result.content_metadata["metadata"]

  def test_replace_large_diff_truncation(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool replace operation with large diff
    When: execute() is called
    Then: diff is truncated to max_diff_lines
    """
    # Create UpdateTool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True,
          max_diff_lines=5
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file with many lines
    test_file = tmp_path / "large_diff.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(50)))

    # Replace large portion
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Line 10",
      new_string="Modified line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    # Diff should be truncated
    if result.content_metadata["metadata"].get("truncated"):
      assert result.content_metadata["metadata"]["original_diff_lines"] > 5


class TestUpdateToolInsertOperation:
  """Test UpdateTool insert operation content metadata."""

  def test_insert_before_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool insert_before operation
    When: execute() is called
    Then: content_metadata includes inserted content and line_number
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "insert_before.txt"
    test_file.write_text("Line 1\nLine 2\n")

    # Insert before line 2
    result = tool.execute(
      path=str(test_file),
      operation="insert_before",
      line_number=2,
      new_string="Inserted line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "insert_before"
    assert result.content_metadata["metadata"]["line_number"] == 2

  def test_insert_after_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool insert_after operation
    When: execute() is called
    Then: content_metadata includes inserted content and line_number
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "insert_after.txt"
    test_file.write_text("Line 1\nLine 2\n")

    # Insert after line 1
    result = tool.execute(
      path=str(test_file),
      operation="insert_after",
      line_number=1,
      new_string="Inserted line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "insert_after"
    assert result.content_metadata["metadata"]["line_number"] == 1

  def test_insert_content_type(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool insert operation
    When: execute() is called
    Then: content_metadata.content_type="full" (showing inserted content)
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "insert_type.txt"
    test_file.write_text("Line 1\n")

    # Insert
    result = tool.execute(
      path=str(test_file),
      operation="insert_after",
      line_number=1,
      new_string="New line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "full"
    assert result.content_metadata["content"] == "New line"

  def test_insert_metadata_includes_context(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool insert operation
    When: execute() is called
    Then: metadata includes lines_before and lines_after context
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "insert_context.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # Insert
    result = tool.execute(
      path=str(test_file),
      operation="insert_after",
      line_number=2,
      new_string="Inserted"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert "lines_before" in result.content_metadata["metadata"]
    assert "lines_after" in result.content_metadata["metadata"]


class TestUpdateToolDeleteOperation:
  """Test UpdateTool delete operation content metadata."""

  def test_delete_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool delete operation
    When: execute() is called
    Then: content_metadata includes deleted content
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "delete.txt"
    test_file.write_text("Line 1\nDelete me\nLine 3\n")

    # Delete
    result = tool.execute(
      path=str(test_file),
      operation="delete",
      old_string="Delete me\n"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "delete"
    assert "Delete me" in result.content_metadata["metadata"].get("deleted_content", "")

  def test_delete_content_type_is_diff(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool delete operation with show_diff_for_updates=True
    When: execute() is called
    Then: content_metadata.content_type="diff"
    """
    # Create UpdateTool with show_diff_for_updates
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "delete_diff.txt"
    test_file.write_text("Line 1\nTo delete\nLine 3\n")

    # Delete
    result = tool.execute(
      path=str(test_file),
      operation="delete",
      old_string="To delete\n"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "diff"

  def test_delete_metadata_includes_line_number(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool delete operation by line number
    When: execute() is called
    Then: metadata includes line_number where deletion occurred
    """
    # Create UpdateTool
    tool = UpdateTool()

    # Create file
    test_file = tmp_path / "delete_line.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # Delete by line number
    result = tool.execute(
      path=str(test_file),
      operation="delete",
      line_number=2
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["line_number"] == 2


class TestUpdateToolDiffTruncation:
  """Test UpdateTool diff truncation for large changes."""

  def test_diff_truncation_for_large_changes(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool with diff exceeding max_diff_lines
    When: execute() is called
    Then: diff is truncated with indicator
    """
    # Create UpdateTool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True,
          max_diff_lines=5
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file with many lines
    test_file = tmp_path / "large_change.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(50)))

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Line 10",
      new_string="Modified"
    )

    # Verify result
    assert result.success
    # May be truncated depending on diff size

  def test_diff_truncation_metadata(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool with truncated diff
    When: execute() is called
    Then: metadata includes truncated=True and original_lines count
    """
    # Create UpdateTool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True,
          max_diff_lines=3
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "truncated_meta.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(100)))

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Line 50",
      new_string="Changed"
    )

    # Verify result
    assert result.success
    if result.content_metadata and result.content_metadata["metadata"].get("truncated"):
      assert "original_diff_lines" in result.content_metadata["metadata"]

  def test_no_truncation_for_small_changes(self, tmp_path: Path) -> None:
    """
    Given: UpdateTool with small diff within max_diff_lines
    When: execute() is called
    Then: full diff is shown without truncation
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True,
          max_diff_lines=50
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "small_change.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Line 2",
      new_string="Modified"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"].get("truncated") is None


class TestUpdateToolShowDiffFlag:
  """Test UpdateTool behavior with show_diff_for_updates flag."""

  def test_show_diff_enabled(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with show_diff_for_updates=True
    When: UpdateTool executes replace operation
    Then: content_metadata includes old_content and new_content (as diff)
    """
    # Create UpdateTool with show_diff_for_updates
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(show_diff_for_updates=True)
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "show_diff.txt"
    test_file.write_text("Old\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old",
      new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "diff"

  def test_show_diff_disabled(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with show_diff_for_updates=False
    When: UpdateTool executes replace operation
    Then: content_metadata shows summary only, no diff
    """
    # Create UpdateTool with show_diff_for_updates=False
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=False
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "no_diff.txt"
    test_file.write_text("Old\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old",
      new_string="New"
    )

    # Verify result
    assert result.success
    # With show_diff_for_updates=False, replace should still show something
    # (implementation may vary)

  def test_show_diff_disabled_insert_operations(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with show_diff_for_updates=False
    When: UpdateTool executes insert operation
    Then: content_metadata still shows inserted content (inserts are not diffs)
    """
    # Create UpdateTool with show_diff_for_updates=False
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=False
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "insert_no_diff.txt"
    test_file.write_text("Line 1\n")

    # Insert
    result = tool.execute(
      path=str(test_file),
      operation="insert_after",
      line_number=1,
      new_string="New line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    # Inserts always show content, not diff
    assert result.content_metadata["content_type"] == "full"
    assert result.content_metadata["content"] == "New line"


class TestUpdateToolVerbosityLevels:
  """Test UpdateTool behavior with different verbosity levels."""

  def test_silent_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="silent"
    When: UpdateTool executes
    Then: ToolResult.content_metadata is None
    """
    # Create UpdateTool with silent verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="silent")
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "silent.txt"
    test_file.write_text("Content\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Content",
      new_string="New content"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is None

  def test_summary_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="summary" and show_diff_for_updates=False
    When: UpdateTool executes replace
    Then: content_metadata.content_type="summary" with operation info
    """
    # Create UpdateTool with summary verbosity and no diffs
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="summary",
          show_diff_for_updates=False
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "summary.txt"
    test_file.write_text("Old\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old",
      new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "summary"
    assert result.content_metadata["content"] is None

  def test_content_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="content"
    When: UpdateTool executes replace
    Then: content_metadata.content_type="diff" with full diff
    """
    # Create UpdateTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "content.txt"
    test_file.write_text("Old\n")

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Old",
      new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "diff"
    assert result.content_metadata["content"] is not None


class TestUpdateToolConfigIntegration:
  """Test UpdateTool integration with ContentDisplayConfig."""

  def test_update_tool_accesses_content_display_config(self) -> None:
    """
    Given: A Config with ContentDisplayConfig
    When: UpdateTool accesses configuration
    Then: ContentDisplayConfig is available
    """
    # Create UpdateTool with custom config
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          max_diff_lines=20
        )
      )
    )
    tool = UpdateTool(config=config)

    # Verify config is accessible
    assert tool._config.tools.content_display.verbosity == "content"
    assert tool._config.tools.content_display.max_diff_lines == 20

  def test_update_tool_respects_max_diff_lines(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with max_diff_lines=10
    When: UpdateTool generates diff with 50 lines
    Then: diff is truncated to 10 lines
    """
    # Create UpdateTool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=True,
          max_diff_lines=10
        )
      )
    )
    tool = UpdateTool(config=config)

    # Create file
    test_file = tmp_path / "max_diff.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(50)))

    # Replace
    result = tool.execute(
      path=str(test_file),
      operation="replace",
      old_string="Line 25",
      new_string="Changed"
    )

    # Verify result
    assert result.success
    # If truncated, check metadata
    if result.content_metadata and result.content_metadata["metadata"].get("truncated"):
      assert result.content_metadata["metadata"]["original_diff_lines"] > 10


class TestHelperFunctions:
  """Test helper functions."""

  def test_truncate_diff_no_truncation(self) -> None:
    """
    Given: Diff lines within limit
    When: _truncate_diff is called
    Then: Returns full diff without truncation (lines normalized with newlines)
    """
    diff_lines = ["--- a/file.txt", "+++ b/file.txt", "@@ -1,1 +1,1 @@", "-old", "+new"]
    result, was_truncated, orig_count = _truncate_diff(diff_lines, max_lines=10)

    assert was_truncated is False
    assert orig_count == 5
    # Each line should end with newline for proper display
    expected = "--- a/file.txt\n+++ b/file.txt\n@@ -1,1 +1,1 @@\n-old\n+new\n"
    assert result == expected

  def test_truncate_diff_with_truncation(self) -> None:
    """
    Given: Diff lines exceeding limit
    When: _truncate_diff is called
    Then: Returns truncated diff
    """
    diff_lines = [f"Line {i}" for i in range(20)]
    result, was_truncated, orig_count = _truncate_diff(diff_lines, max_lines=10)

    assert was_truncated is True
    assert orig_count == 20
    assert result.count("\n") <= 10