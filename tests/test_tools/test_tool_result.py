"""Tests for ToolResult content_metadata field.

Task: 1.5.5 - Show Write/Update Tool Content in CLI
"""

from yoker.tools.base import ToolResult


class TestToolResultContentMetadata:
  """Test ToolResult with content_metadata field."""

  def test_tool_result_with_content_metadata(self) -> None:
    """
    Given: A tool result with content metadata
    When: Creating ToolResult with content_metadata
    Then: content_metadata field is populated
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "full",
        "content": "test content",
        "metadata": {"lines": 1, "is_new_file": True},
      },
    )

    assert result.success is True
    assert result.result == "File written successfully"
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "write"
    assert result.content_metadata["path"] == "/tmp/test.py"
    assert result.content_metadata["content_type"] == "full"

  def test_content_metadata_fields(self) -> None:
    """
    Given: A ToolResult with content_metadata
    When: Accessing content_metadata fields
    Then: operation, path, content_type, content, metadata are available
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "full",
        "content": "test content",
        "metadata": {"lines": 1, "byte_size": 12},
      },
    )

    assert result.content_metadata is not None
    assert "operation" in result.content_metadata
    assert "path" in result.content_metadata
    assert "content_type" in result.content_metadata
    assert "content" in result.content_metadata
    assert "metadata" in result.content_metadata

  def test_content_metadata_optional_content(self) -> None:
    """
    Given: A ToolResult with content_type="summary"
    When: Creating ToolResult
    Then: content field can be None (only metadata present)
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "summary",
        "content": None,
        "metadata": {"lines": 1, "is_new_file": True},
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["content"] is None

  def test_content_metadata_dict_type(self) -> None:
    """
    Given: A ToolResult with content_metadata
    When: Checking content_metadata type
    Then: It is a dict[str, Any]
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "full",
      },
    )

    assert result.content_metadata is not None
    assert isinstance(result.content_metadata, dict)


class TestToolResultBackwardsCompatibility:
  """Test ToolResult backwards compatibility without content_metadata."""

  def test_tool_result_without_content_metadata(self) -> None:
    """
    Given: A tool result without content metadata
    When: Creating ToolResult without content_metadata
    Then: content_metadata is None (backwards compatible)
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
    )

    assert result.success is True
    assert result.result == "File written successfully"
    assert result.content_metadata is None

  def test_tool_result_default_content_metadata(self) -> None:
    """
    Given: A ToolResult created with default values
    When: Checking content_metadata
    Then: content_metadata defaults to None
    """
    result = ToolResult(success=True, result="Success")

    assert result.content_metadata is None

  def test_tool_result_success_only(self) -> None:
    """
    Given: A legacy ToolResult with only success and result
    When: Creating ToolResult(success=True, result="...")
    Then: content_metadata is None and result is available
    """
    result = ToolResult(success=True, result="Operation completed")

    assert result.success is True
    assert result.result == "Operation completed"
    assert result.content_metadata is None

  def test_tool_result_error_only(self) -> None:
    """
    Given: A legacy ToolResult with error
    When: Creating ToolResult(success=False, error="...")
    Then: content_metadata is None and error is available
    """
    result = ToolResult(
      success=False,
      result="",
      error="Permission denied",
    )

    assert result.success is False
    assert result.error == "Permission denied"
    assert result.content_metadata is None


class TestToolResultContentMetadataWrite:
  """Test content_metadata for write operations."""

  def test_write_content_metadata_new_file(self) -> None:
    """
    Given: A write operation creating a new file
    When: ToolResult includes content_metadata
    Then: metadata includes is_new_file=True
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "full",
        "content": "test content",
        "metadata": {"lines": 1, "is_new_file": True},
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["is_new_file"] is True

  def test_write_content_metadata_overwrite(self) -> None:
    """
    Given: A write operation overwriting existing file
    When: ToolResult includes content_metadata
    Then: metadata includes is_overwrite=True
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "full",
        "content": "test content",
        "metadata": {"lines": 1, "is_overwrite": True},
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["is_overwrite"] is True

  def test_write_content_metadata_line_count(self) -> None:
    """
    Given: A write operation with content
    When: ToolResult includes content_metadata
    Then: metadata includes lines=N
    """
    result = ToolResult(
      success=True,
      result="File written successfully",
      content_metadata={
        "operation": "write",
        "path": "/tmp/test.py",
        "content_type": "full",
        "content": "line1\nline2\nline3\n",
        "metadata": {"lines": 3},
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["lines"] == 3


class TestToolResultContentMetadataUpdate:
  """Test content_metadata for update operations."""

  def test_update_replace_diff_metadata(self) -> None:
    """
    Given: An update replace operation
    When: ToolResult includes content_metadata
    Then: metadata includes old_content and new_content
    """
    result = ToolResult(
      success=True,
      result="File updated successfully",
      content_metadata={
        "operation": "replace",
        "path": "/tmp/test.py",
        "content_type": "diff",
        "content": "-old line\n+new line\n",
        "metadata": {
          "old_content": "old line",
          "new_content": "new line",
          "lines_modified": 1,
        },
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["old_content"] == "old line"
    assert result.content_metadata["metadata"]["new_content"] == "new line"

  def test_update_insert_metadata(self) -> None:
    """
    Given: An update insert operation
    When: ToolResult includes content_metadata
    Then: metadata includes inserted content and line_number
    """
    result = ToolResult(
      success=True,
      result="File updated successfully",
      content_metadata={
        "operation": "insert_after",
        "path": "/tmp/test.py",
        "content_type": "full",
        "content": "new line\n",
        "metadata": {"line_number": 5},
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["line_number"] == 5

  def test_update_delete_metadata(self) -> None:
    """
    Given: An update delete operation
    When: ToolResult includes content_metadata
    Then: metadata includes deleted content
    """
    result = ToolResult(
      success=True,
      result="File updated successfully",
      content_metadata={
        "operation": "delete",
        "path": "/tmp/test.py",
        "content_type": "diff",
        "content": "-deleted line\n",
        "metadata": {"deleted_content": "deleted line"},
      },
    )

    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["deleted_content"] == "deleted line"
