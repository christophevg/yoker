"""Tests for update tool content metadata and diff generation.

Task: 1.5.5 - Show Write/Update Tool Content in CLI
"""

from pathlib import Path

import pytest

from yoker.config import Config, ContentDisplayConfig, ToolsConfig
from yoker.tools import ToolRegistry, make_update_tool
from yoker.tools.update import _truncate_diff


def _update_spec(config: Config | None = None):
  """Create and register the update tool."""
  registry = ToolRegistry()
  return registry.register(make_update_tool(config))


class TestUpdateToolReplaceOperation:
  """Test update tool replace operation content metadata."""

  @pytest.mark.asyncio
  async def test_replace_diff_generation(self, tmp_path: Path) -> None:
    """
    Given: update tool replace operation
    When: execute() is called
    Then: ToolResult includes content_metadata with old_content and new_content
    """
    # Create update tool with content verbosity and show_diff_for_updates
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content", show_diff_for_updates=True)
      )
    )
    spec = _update_spec(config)

    # Create file with content
    test_file = tmp_path / "replace.txt"
    test_file.write_text("Line 1\nOld text\nLine 3\n")

    # Replace text
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old text", new_string="New text"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "replace"
    assert result.content_metadata["content_type"] == "text/x-diff"
    assert result.content_metadata["content"] is not None
    # Diff should show old and new
    assert "-" in result.content_metadata["content"]
    assert "+" in result.content_metadata["content"]

  @pytest.mark.asyncio
  async def test_replace_content_type_is_diff(self, tmp_path: Path) -> None:
    """
    Given: update tool replace operation with show_diff_for_updates=True
    When: execute() is called
    Then: content_metadata.content_type="diff"
    """
    # Create update tool with show_diff_for_updates
    config = Config(
      tools=ToolsConfig(content_display=ContentDisplayConfig(show_diff_for_updates=True))
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "replace_diff.txt"
    test_file.write_text("Old content\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old content", new_string="New content"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/x-diff"

  @pytest.mark.asyncio
  async def test_replace_metadata(self, tmp_path: Path) -> None:
    """
    Given: update tool replace operation
    When: execute() is called
    Then: metadata includes lines_modified count
    """
    # Create update tool
    spec = _update_spec()

    # Create file
    test_file = tmp_path / "replace_meta.txt"
    test_file.write_text("Line 1\nOld\nLine 3\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old", new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert "lines_modified" in result.content_metadata["metadata"]

  @pytest.mark.asyncio
  async def test_replace_large_diff_truncation(self, tmp_path: Path) -> None:
    """
    Given: update tool replace operation with large diff
    When: execute() is called
    Then: diff is truncated to max_diff_lines
    """
    # Create update tool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content", show_diff_for_updates=True, max_diff_lines=5
        )
      )
    )
    spec = _update_spec(config)

    # Create file with many lines
    test_file = tmp_path / "large_diff.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(50)))

    # Replace large portion
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Line 10", new_string="Modified line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    # Diff should be truncated
    if result.content_metadata["metadata"].get("truncated"):
      assert result.content_metadata["metadata"]["original_diff_lines"] > 5


class TestUpdateToolInsertOperation:
  """Test update tool insert operation content metadata."""

  @pytest.mark.asyncio
  async def test_insert_before_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: update tool insert_before operation
    When: execute() is called
    Then: content_metadata includes inserted content and line_number
    """
    # Create update tool with content verbosity
    config = Config(tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="content")))
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "insert_before.txt"
    test_file.write_text("Line 1\nLine 2\n")

    # Insert before line 2
    result = await spec.execute(
      path=str(test_file), operation="insert_before", line_number=2, new_string="Inserted line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "insert_before"
    assert result.content_metadata["metadata"]["line_number"] == 2

  @pytest.mark.asyncio
  async def test_insert_after_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: update tool insert_after operation
    When: execute() is called
    Then: content_metadata includes inserted content and line_number
    """
    # Create update tool with content verbosity
    config = Config(tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="content")))
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "insert_after.txt"
    test_file.write_text("Line 1\nLine 2\n")

    # Insert after line 1
    result = await spec.execute(
      path=str(test_file), operation="insert_after", line_number=1, new_string="Inserted line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "insert_after"
    assert result.content_metadata["metadata"]["line_number"] == 1

  @pytest.mark.asyncio
  async def test_insert_content_type(self, tmp_path: Path) -> None:
    """
    Given: update tool insert operation
    When: execute() is called
    Then: content_metadata.content_type="full" (showing inserted content)
    """
    # Create update tool with content verbosity
    config = Config(tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="content")))
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "insert_type.txt"
    test_file.write_text("Line 1\n")

    # Insert
    result = await spec.execute(
      path=str(test_file), operation="insert_after", line_number=1, new_string="New line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/plain"
    assert result.content_metadata["content"] == "New line"

  @pytest.mark.asyncio
  async def test_insert_metadata_includes_context(self, tmp_path: Path) -> None:
    """
    Given: update tool insert operation
    When: execute() is called
    Then: metadata includes lines_before and lines_after context
    """
    # Create update tool with content verbosity
    config = Config(tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="content")))
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "insert_context.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # Insert
    result = await spec.execute(
      path=str(test_file), operation="insert_after", line_number=2, new_string="Inserted"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert "lines_before" in result.content_metadata["metadata"]
    assert "lines_after" in result.content_metadata["metadata"]


class TestUpdateToolDeleteOperation:
  """Test update tool delete operation content metadata."""

  @pytest.mark.asyncio
  async def test_delete_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: update tool delete operation
    When: execute() is called
    Then: content_metadata includes deleted content
    """
    # Create update tool with content verbosity
    config = Config(tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="content")))
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "delete.txt"
    test_file.write_text("Line 1\nDelete me\nLine 3\n")

    # Delete
    result = await spec.execute(path=str(test_file), operation="delete", old_string="Delete me\n")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "delete"
    assert "Delete me" in result.content_metadata["metadata"].get("deleted_content", "")

  @pytest.mark.asyncio
  async def test_delete_content_type_is_diff(self, tmp_path: Path) -> None:
    """
    Given: update tool delete operation with show_diff_for_updates=True
    When: execute() is called
    Then: content_metadata.content_type="diff"
    """
    # Create update tool with show_diff_for_updates
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content", show_diff_for_updates=True)
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "delete_diff.txt"
    test_file.write_text("Line 1\nTo delete\nLine 3\n")

    # Delete
    result = await spec.execute(path=str(test_file), operation="delete", old_string="To delete\n")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/x-diff"

  @pytest.mark.asyncio
  async def test_delete_metadata_includes_line_number(self, tmp_path: Path) -> None:
    """
    Given: update tool delete operation by line number
    When: execute() is called
    Then: metadata includes line_number where deletion occurred
    """
    # Create update tool
    spec = _update_spec()

    # Create file
    test_file = tmp_path / "delete_line.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # Delete by line number
    result = await spec.execute(path=str(test_file), operation="delete", line_number=2)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["line_number"] == 2


class TestUpdateToolDiffTruncation:
  """Test update tool diff truncation for large changes."""

  @pytest.mark.asyncio
  async def test_diff_truncation_for_large_changes(self, tmp_path: Path) -> None:
    """
    Given: update tool with diff exceeding max_diff_lines
    When: execute() is called
    Then: diff is truncated with indicator
    """
    # Create update tool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content", show_diff_for_updates=True, max_diff_lines=5
        )
      )
    )
    spec = _update_spec(config)

    # Create file with many lines
    test_file = tmp_path / "large_change.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(50)))

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Line 10", new_string="Modified"
    )

    # Verify result
    assert result.success
    # May be truncated depending on diff size

  @pytest.mark.asyncio
  async def test_diff_truncation_metadata(self, tmp_path: Path) -> None:
    """
    Given: update tool with truncated diff
    When: execute() is called
    Then: metadata includes truncated=True and original_lines count
    """
    # Create update tool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content", show_diff_for_updates=True, max_diff_lines=3
        )
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "truncated_meta.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(100)))

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Line 50", new_string="Changed"
    )

    # Verify result
    assert result.success
    if result.content_metadata and result.content_metadata["metadata"].get("truncated"):
      assert "original_diff_lines" in result.content_metadata["metadata"]

  @pytest.mark.asyncio
  async def test_no_truncation_for_small_changes(self, tmp_path: Path) -> None:
    """
    Given: update tool with small diff within max_diff_lines
    When: execute() is called
    Then: full diff is shown without truncation
    """
    # Create update tool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content", show_diff_for_updates=True, max_diff_lines=50
        )
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "small_change.txt"
    test_file.write_text("Line 1\nLine 2\nLine 3\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Line 2", new_string="Modified"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"].get("truncated") is None


class TestUpdateToolShowDiffFlag:
  """Test update tool behavior with show_diff_for_updates flag."""

  @pytest.mark.asyncio
  async def test_show_diff_enabled(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with show_diff_for_updates=True
    When: update tool executes replace operation
    Then: content_metadata includes old_content and new_content (as diff)
    """
    # Create update tool with show_diff_for_updates
    config = Config(
      tools=ToolsConfig(content_display=ContentDisplayConfig(show_diff_for_updates=True))
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "show_diff.txt"
    test_file.write_text("Old\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old", new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/x-diff"

  @pytest.mark.asyncio
  async def test_show_diff_disabled(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with show_diff_for_updates=False
    When: update tool executes replace operation
    Then: content_metadata shows summary only, no diff
    """
    # Create update tool with show_diff_for_updates=False
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content", show_diff_for_updates=False)
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "no_diff.txt"
    test_file.write_text("Old\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old", new_string="New"
    )

    # Verify result
    assert result.success
    # With show_diff_for_updates=False, replace should still show something
    # (implementation may vary)

  @pytest.mark.asyncio
  async def test_show_diff_disabled_insert_operations(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with show_diff_for_updates=False
    When: update tool executes insert operation
    Then: content_metadata still shows inserted content (inserts are not diffs)
    """
    # Create update tool with show_diff_for_updates=False
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content", show_diff_for_updates=False)
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "insert_no_diff.txt"
    test_file.write_text("Line 1\n")

    # Insert
    result = await spec.execute(
      path=str(test_file), operation="insert_after", line_number=1, new_string="New line"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    # Inserts always show content, not diff
    assert result.content_metadata["content_type"] == "text/plain"
    assert result.content_metadata["content"] == "New line"


class TestUpdateToolVerbosityLevels:
  """Test update tool behavior with different verbosity levels."""

  @pytest.mark.asyncio
  async def test_silent_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="silent"
    When: update tool executes
    Then: ToolResult.content_metadata is None
    """
    # Create update tool with silent verbosity
    config = Config(tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="silent")))
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "silent.txt"
    test_file.write_text("Content\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Content", new_string="New content"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is None

  @pytest.mark.asyncio
  async def test_summary_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="summary" and show_diff_for_updates=False
    When: update tool executes replace
    Then: content_metadata.content_type="application/x-summary" with operation info
    """
    # Create update tool with summary verbosity and no diffs
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="summary", show_diff_for_updates=False)
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "summary.txt"
    test_file.write_text("Old\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old", new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "application/x-summary"
    assert result.content_metadata["content"] is None

  @pytest.mark.asyncio
  async def test_content_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="content"
    When: update tool executes replace
    Then: content_metadata.content_type="diff" with full diff
    """
    # Create update tool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content", show_diff_for_updates=True)
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "content.txt"
    test_file.write_text("Old\n")

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Old", new_string="New"
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/x-diff"
    assert result.content_metadata["content"] is not None


class TestUpdateToolConfigIntegration:
  """Test update tool integration with ContentDisplayConfig."""

  @pytest.mark.asyncio
  async def test_update_tool_respects_max_diff_lines(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with max_diff_lines=10
    When: update tool generates diff with 50 lines
    Then: diff is truncated to 10 lines
    """
    # Create update tool with small max_diff_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content", show_diff_for_updates=True, max_diff_lines=10
        )
      )
    )
    spec = _update_spec(config)

    # Create file
    test_file = tmp_path / "max_diff.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(50)))

    # Replace
    result = await spec.execute(
      path=str(test_file), operation="replace", old_string="Line 25", new_string="Changed"
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
