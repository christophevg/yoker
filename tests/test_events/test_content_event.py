"""Tests for ToolContentEvent creation and handling.

Task: 1.5.5 - Show Write/Update Tool Content in CLI
"""

from datetime import datetime

import pytest

from yoker.events.types import Event, EventType, ToolContentEvent


class TestToolContentEventCreation:
  """Test ToolContentEvent creation with various content types."""

  def test_content_event_creation_with_full_content(self) -> None:
    """
    Given: A tool operation with full content to display
    When: Creating a ToolContentEvent with content_type="full"
    Then: Event contains complete content and metadata
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content="def hello():\n    print('Hello')\n",
      metadata={"lines": 3, "is_new_file": True},
    )

    assert event.tool_name == "write"
    assert event.operation == "write"
    assert event.path == "/tmp/test.py"
    assert event.content_type == "full"
    assert event.content == "def hello():\n    print('Hello')\n"
    assert event.metadata["lines"] == 3
    assert event.metadata["is_new_file"] is True

  def test_content_event_creation_with_diff_content(self) -> None:
    """
    Given: A tool operation with diff content to display
    When: Creating a ToolContentEvent with content_type="diff"
    Then: Event contains old_content, new_content, and metadata
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/tmp/test.py",
      content_type="diff",
      content="-old line\n+new line\n",
      metadata={
        "old_content": "old line",
        "new_content": "new line",
        "lines_modified": 1,
      },
    )

    assert event.tool_name == "update"
    assert event.operation == "replace"
    assert event.content_type == "diff"
    assert event.metadata["old_content"] == "old line"
    assert event.metadata["new_content"] == "new line"
    assert event.metadata["lines_modified"] == 1

  def test_content_event_creation_with_summary_content(self) -> None:
    """
    Given: A tool operation with summary content to display
    When: Creating a ToolContentEvent with content_type="summary"
    Then: Event contains summary metadata without full content
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="summary",
      content=None,
      metadata={"lines": 10, "is_new_file": True},
    )

    assert event.content_type == "summary"
    assert event.content is None
    assert event.metadata["lines"] == 10

  def test_content_event_with_write_operation(self) -> None:
    """
    Given: A write tool operation
    When: Creating a ToolContentEvent
    Then: operation field is "write" and metadata includes create/overwrite status
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content="test content",
      metadata={"is_new_file": True},
    )

    assert event.operation == "write"
    assert event.metadata["is_new_file"] is True

  def test_content_event_with_replace_operation(self) -> None:
    """
    Given: An update tool replace operation
    When: Creating a ToolContentEvent
    Then: operation field is "replace" and metadata includes old/new content
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="replace",
      path="/tmp/test.py",
      content_type="diff",
      content="-old\n+new\n",
      metadata={"old_content": "old", "new_content": "new"},
    )

    assert event.operation == "replace"
    assert event.metadata["old_content"] == "old"
    assert event.metadata["new_content"] == "new"

  def test_content_event_with_insert_operation(self) -> None:
    """
    Given: An update tool insert operation
    When: Creating a ToolContentEvent
    Then: operation field is "insert_before" or "insert_after" with line_number
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="insert_after",
      path="/tmp/test.py",
      content_type="full",
      content="new line\n",
      metadata={"line_number": 5},
    )

    assert event.operation == "insert_after"
    assert event.metadata["line_number"] == 5

  def test_content_event_with_delete_operation(self) -> None:
    """
    Given: An update tool delete operation
    When: Creating a ToolContentEvent
    Then: operation field is "delete" and metadata includes deleted content
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="update",
      operation="delete",
      path="/tmp/test.py",
      content_type="diff",
      content="-deleted line\n",
      metadata={"deleted_content": "deleted line"},
    )

    assert event.operation == "delete"
    assert event.metadata["deleted_content"] == "deleted line"


class TestToolContentEventMetadata:
  """Test event metadata handling for content events."""

  def test_metadata_includes_line_count(self) -> None:
    """
    Given: Content with multiple lines
    When: Creating ToolContentEvent
    Then: metadata includes accurate line_count
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content="line1\nline2\nline3\n",
      metadata={"lines": 3},
    )

    assert event.metadata["lines"] == 3

  def test_metadata_includes_byte_size(self) -> None:
    """
    Given: Content with known byte size
    When: Creating ToolContentEvent
    Then: metadata includes byte_size
    """
    content = "test content"
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content=content,
      metadata={"byte_size": len(content.encode("utf-8"))},
    )

    assert event.metadata["byte_size"] == 12

  def test_metadata_includes_truncation_info(self) -> None:
    """
    Given: Content that was truncated
    When: Creating ToolContentEvent
    Then: metadata includes truncated=True and original_line_count
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content="line1\nline2\n",
      metadata={"lines": 2, "truncated": True, "original_line_count": 100},
    )

    assert event.metadata["truncated"] is True
    assert event.metadata["original_line_count"] == 100

  def test_metadata_for_new_file(self) -> None:
    """
    Given: A write operation creating a new file
    When: Creating ToolContentEvent
    Then: metadata includes is_new_file=True
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content="content",
      metadata={"is_new_file": True},
    )

    assert event.metadata["is_new_file"] is True

  def test_metadata_for_overwrite(self) -> None:
    """
    Given: A write operation overwriting existing file
    When: Creating ToolContentEvent
    Then: metadata includes is_overwrite=True
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
      content="content",
      metadata={"is_overwrite": True},
    )

    assert event.metadata["is_overwrite"] is True


class TestToolContentEventType:
  """Test that ToolContentEvent is properly registered as event type."""

  def test_event_type_registered(self) -> None:
    """
    Given: The EventType enum
    When: Checking for TOOL_CONTENT
    Then: EventType.TOOL_CONTENT exists
    """
    assert hasattr(EventType, "TOOL_CONTENT")
    assert EventType.TOOL_CONTENT is not None

  def test_content_event_is_frozen(self) -> None:
    """
    Given: A ToolContentEvent instance
    When: Attempting to modify fields
    Then: Event is immutable (frozen dataclass)
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
    )

    with pytest.raises(AttributeError):
      event.tool_name = "update"  # type: ignore[misc]

  def test_content_event_inherits_from_event(self) -> None:
    """
    Given: A ToolContentEvent instance
    When: Checking type hierarchy
    Then: Event inherits from base Event class
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="write",
      operation="write",
      path="/tmp/test.py",
      content_type="full",
    )

    assert isinstance(event, Event)
    assert hasattr(event, "type")
    assert hasattr(event, "timestamp")
    assert isinstance(event.timestamp, datetime)
