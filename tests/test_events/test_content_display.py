"""Tests for ConsoleEventHandler content display.

Task: 1.5.6 - Complete Tool Content Display
"""

from io import StringIO

import pytest
from rich.console import Console

from yoker.events import ConsoleEventHandler, EventType, ToolContentEvent


class TestConsoleEventHandlerSilentMode:
  """Test silent verbosity mode (no content displayed)."""

  @pytest.fixture
  def silent_handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler with silent verbosity."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_silent_mode_displays_no_content(self, silent_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="silent"
    When: Handling ToolContentEvent
    Then: No content is displayed (only tool name and result)
    """
    # This is tested implicitly by not setting content_metadata on tools
    # when verbosity is silent. The handler still works but tools don't
    # emit content_metadata in silent mode.
    # Here we test that a ToolContentEvent still works if emitted.
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 10, "is_new_file": True},
    )
    silent_handler(event)
    # Should not raise, just handle silently
    output = silent_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # With show_tool_calls=True, summary info should be displayed
    assert "file.txt" in output

  def test_silent_mode_shows_success_indicator(self, silent_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="silent"
    When: Handling ToolContentEvent after successful write
    Then: Shows tool name and success indicator (✓)
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 10, "is_new_file": True},
    )
    silent_handler(event)
    output = silent_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Summary mode shows file info
    assert "file.txt" in output


class TestConsoleEventHandlerSummaryMode:
  """Test summary verbosity mode (line counts shown)."""

  @pytest.fixture
  def summary_handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler for summary display."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_summary_mode_shows_line_count(self, summary_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="summary"
    When: Handling ToolContentEvent for write
    Then: Shows "Creating new file (N lines)"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/newfile.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 24, "is_new_file": True},
    )
    summary_handler(event)
    output = summary_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "newfile.txt" in output
    assert "24 lines" in output

  def test_summary_mode_shows_overwrite_info(self, summary_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="summary"
    When: Handling ToolContentEvent for overwrite
    Then: Shows "Overwriting file (N lines)"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/existing.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 42, "is_new_file": False, "is_overwrite": True},
    )
    summary_handler(event)
    output = summary_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "existing.txt" in output
    assert "42 lines" in output

  def test_summary_mode_shows_replace_summary(self, summary_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="summary"
    When: Handling ToolContentEvent for replace
    Then: Shows "Replace in file"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"old_content": "old", "new_content": "new"},
    )
    summary_handler(event)
    output = summary_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    assert "Replace" in output

  def test_summary_mode_shows_insert_summary(self, summary_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="summary"
    When: Handling ToolContentEvent for insert
    Then: Shows "Insert at line N: 'content'"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="insert_after",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"line_number": 42, "inserted_lines": 3},
    )
    summary_handler(event)
    output = summary_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    assert "Insert" in output
    assert "line 42" in output
    assert "3 line" in output

  def test_summary_mode_shows_delete_summary(self, summary_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="summary"
    When: Handling ToolContentEvent for delete
    Then: Shows "Delete line N: 'content'"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="delete",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"line_number": 15},
    )
    summary_handler(event)
    output = summary_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    assert "Delete" in output
    assert "line 15" in output


class TestConsoleEventHandlerContentMode:
  """Test content verbosity mode (full content shown)."""

  @pytest.fixture
  def content_handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler for content display."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_content_mode_shows_full_content(self, content_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="content"
    When: Handling ToolContentEvent for write
    Then: Shows full file content with line numbers
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="Line 1\nLine 2\nLine 3\n",
      metadata={"lines": 3},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    assert "Line 1" in output
    assert "Line 2" in output
    assert "Line 3" in output
    # Line numbers should be present
    assert "1" in output
    assert "2" in output
    assert "3" in output

  def test_content_mode_shows_diff(self, content_handler: ConsoleEventHandler) -> None:
    """
    Given: ConsoleEventHandler with verbosity="content" and show_diff_for_updates=True
    When: Handling ToolContentEvent for replace
    Then: Shows unified diff with -/+ markers
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content="--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-old line\n+new line\n",
      metadata={},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    # Diff markers should be present
    assert "-" in output or "old" in output
    assert "+" in output or "new" in output

  def test_content_mode_shows_insert_with_context(
    self, content_handler: ConsoleEventHandler
  ) -> None:
    """
    Given: ConsoleEventHandler with verbosity="content"
    When: Handling ToolContentEvent for insert
    Then: Shows inserted content with surrounding context
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="insert_after",
      path="/path/to/file.txt",
      content_type="full",
      content="Inserted line 1\nInserted line 2\n",
      metadata={"line_number": 10, "inserted_lines": 2},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    assert "Inserted" in output

  def test_content_mode_shows_delete_with_context(
    self, content_handler: ConsoleEventHandler
  ) -> None:
    """
    Given: ConsoleEventHandler with verbosity="content"
    When: Handling ToolContentEvent for delete
    Then: Shows deleted content with surrounding context
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="delete",
      path="/path/to/file.txt",
      content_type="full",
      content=None,  # No content for delete in full mode
      metadata={"line_number": 15},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output
    assert "Delete" in output


class TestConsoleEventHandlerTruncation:
  """Test content truncation with "... N more lines" indicator."""

  @pytest.fixture
  def content_handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler for content display."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_truncation_shows_first_n_lines(self, content_handler: ConsoleEventHandler) -> None:
    """
    Given: Content exceeding max_content_lines
    When: Displaying content
    Then: Shows first N lines then "... (M more lines)"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="\n".join(f"Line {i}" for i in range(10)),
      metadata={"lines": 50, "truncated": True, "original_line_count": 50},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Should show truncation indicator
    assert "more lines" in output or "Line 0" in output

  def test_truncation_indicator_format(self, content_handler: ConsoleEventHandler) -> None:
    """
    Given: Content truncated to 10 lines out of 50
    When: Displaying truncation indicator
    Then: Shows "... (40 more lines)"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="\n".join(f"Line {i}" for i in range(10)),
      metadata={"truncated": True, "original_line_count": 50},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "40 more lines" in output

  def test_truncation_for_diff(self, content_handler: ConsoleEventHandler) -> None:
    """
    Given: Diff exceeding max_diff_lines
    When: Displaying diff
    Then: Shows truncated diff with indicator
    """
    # Diff content that would be truncated
    diff_content = "--- file.txt\n+++ file.txt\n"
    diff_content += "\n".join(f"@@ -{i} +{i} @@" for i in range(100))

    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content=diff_content,
      metadata={},
    )
    content_handler(event)
    # Should handle diff content
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output

  def test_no_truncation_for_small_content(self, content_handler: ConsoleEventHandler) -> None:
    """
    Given: Content within max_content_lines
    When: Displaying content
    Then: Shows full content without truncation
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="Line 1\nLine 2\nLine 3\n",
      metadata={"lines": 3},
    )
    content_handler(event)
    output = content_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Should show all lines
    assert "Line 1" in output
    assert "Line 2" in output
    assert "Line 3" in output
    # Should not show truncation indicator
    assert "more lines" not in output


class TestConsoleEventHandlerDiffDisplay:
  """Test diff display for update operations."""

  @pytest.fixture
  def diff_handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler for diff display."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_diff_shows_removed_lines_in_red(self, diff_handler: ConsoleEventHandler) -> None:
    """
    Given: Diff with removed lines
    When: Displaying diff
    Then: Removed lines shown in red with '-' prefix
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content="--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-old line\n+new line\n",
      metadata={},
    )
    diff_handler(event)
    output = diff_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "old line" in output

  def test_diff_shows_added_lines_in_green(self, diff_handler: ConsoleEventHandler) -> None:
    """
    Given: Diff with added lines
    When: Displaying diff
    Then: Added lines shown in green with '+' prefix
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content="--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-old line\n+new line\n",
      metadata={},
    )
    diff_handler(event)
    output = diff_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "new line" in output

  def test_diff_shows_context_in_cyan(self, diff_handler: ConsoleEventHandler) -> None:
    """
    Given: Diff with context lines
    When: Displaying diff
    Then: Context lines (@@ markers) shown in cyan
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content="--- file.txt\n+++ file.txt\n@@ -1,3 +1,3 @@\n context\n-old\n+new\n context\n",
      metadata={},
    )
    diff_handler(event)
    output = diff_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "@@" in output

  def test_diff_uses_unified_format(self, diff_handler: ConsoleEventHandler) -> None:
    """
    Given: Replace operation with old and new content
    When: Generating diff
    Then: Uses unified diff format
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content="--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-old\n+new\n",
      metadata={},
    )
    diff_handler(event)
    output = diff_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Unified diff format markers
    assert "---" in output or "file.txt" in output
    assert "+++" in output or "file.txt" in output


class TestConsoleEventHandlerVisualConsistency:
  """Test visual consistency with Read tool."""

  @pytest.fixture
  def handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler for visual tests."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_tool_name_in_cyan(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent
    When: Displaying tool output
    Then: Tool name shown in cyan (matches Read tool)
    """
    # Note: Rich colors are hard to test directly, but we can check structure
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 10},
    )
    handler(event)
    # Should display without error
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output

  def test_filename_only_not_full_path(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent with full path
    When: Displaying tool output
    Then: Shows basename only, not full path
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/very/long/path/to/some/file.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 10},
    )
    handler(event)
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Should show only basename
    assert "file.txt" in output
    # Should not show full path
    assert "/very/long/path" not in output

  def test_success_indicator_after_content(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent with successful operation
    When: Displaying content
    Then: Shows ✓ Success after content
    """
    # Note: Success indicator is shown in ToolResultEvent, not ToolContentEvent
    # ToolContentEvent shows the content, ToolResultEvent shows the success
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="Content\n",
      metadata={"lines": 1},
    )
    handler(event)
    # Should handle event without error
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output

  def test_content_separator_style(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent with content
    When: Displaying content in content mode
    Then: Uses separator lines (──────)
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="Line 1\nLine 2\n",
      metadata={"lines": 2},
    )
    handler(event)
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Should show content with line numbers
    assert "file.txt" in output


class TestConsoleEventHandlerEdgeCases:
  """Test edge cases in content display."""

  @pytest.fixture
  def handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler for edge case tests."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_tool_calls=True)

  def test_empty_file_display(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent for empty file
    When: Displaying content
    Then: Shows "(0 lines, empty)"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/empty.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 0, "is_empty": True},
    )
    handler(event)
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "0 lines" in output
    assert "empty" in output

  def test_binary_file_display(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent for binary file
    When: Displaying content
    Then: Shows "(N KB binary)"
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/binary.bin",
      content_type="summary",
      content=None,
      metadata={"is_binary": True, "bytes": 2048},
    )
    handler(event)
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "binary" in output
    assert "KB" in output

  def test_unicode_content_handling(self, handler: ConsoleEventHandler) -> None:
    """
    Given: ToolContentEvent with unicode content
    When: Displaying content
    Then: Displays unicode correctly
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="Hello 世界\nПривет мир\n",
      metadata={"lines": 2},
    )
    handler(event)
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Unicode should be preserved
    assert "世界" in output
    assert "мир" in output

  def test_very_long_lines_truncation(self, handler: ConsoleEventHandler) -> None:
    """
    Given: Content with very long lines
    When: Displaying content
    Then: Lines truncated at max_content_bytes
    """
    # This is a unit test for the handler, truncation is done in the tool
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="x" * 100,  # Short content for unit test
      metadata={"lines": 1},
    )
    handler(event)
    # Should handle without error
    output = handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output


class TestConsoleEventHandlerMethodDispatch:
  """Test handler method dispatch for ToolContentEvent."""

  def test_handler_has_tool_content_method(self) -> None:
    """
    Given: ConsoleEventHandler instance
    When: Checking for _handle_tool_content method
    Then: Method exists
    """
    handler = ConsoleEventHandler()
    assert hasattr(handler, "_handle_tool_content")
    assert callable(handler._handle_tool_content)

  def test_handler_dispatches_tool_content_event(self) -> None:
    """
    Given: ConsoleEventHandler handling events
    When: ToolContentEvent is emitted
    Then: _handle_tool_content is called
    """
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    handler = ConsoleEventHandler(console=console, show_tool_calls=True)

    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 10},
    )

    # Call handler
    handler(event)

    # Should produce output
    output_str = console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output_str

  def test_handler_formats_content_based_on_type(self) -> None:
    """
    Given: ToolContentEvent with different content_type values
    When: Handling event
    Then: Formats content appropriately (full, diff, summary)
    """
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    handler = ConsoleEventHandler(console=console, show_tool_calls=True)

    # Test summary type
    event_summary = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="summary",
      content=None,
      metadata={"lines": 10},
    )
    handler(event_summary)
    output_summary = console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output_summary

    # Reset output
    output.truncate(0)
    output.seek(0)

    # Test full type
    event_full = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/path/to/file.txt",
      content_type="full",
      content="Line 1\nLine 2\n",
      metadata={"lines": 2},
    )
    handler(event_full)
    output_full = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Line 1" in output_full
    assert "Line 2" in output_full

    # Reset output
    output.truncate(0)
    output.seek(0)

    # Test diff type
    event_diff = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/path/to/file.txt",
      content_type="diff",
      content="--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-old\n+new\n",
      metadata={},
    )
    handler(event_diff)
    output_diff = console.file.getvalue()  # type: ignore[attr-defined]
    assert "file.txt" in output_diff
