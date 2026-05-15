"""Tests for WriteTool content metadata emission.

Task: 1.5.5 - Show Write/Update Tool Content in CLI
"""

from pathlib import Path

from yoker.config.schema import (
  Config,
  ContentDisplayConfig,
  ToolsConfig,
  WriteToolConfig,
)
from yoker.tools.write import WriteTool, _is_binary, _truncate_content


class TestWriteToolContentMetadataEmission:
  """Test WriteTool content metadata emission."""

  def test_content_metadata_for_new_file(self, tmp_path: Path) -> None:
    """
    Given: WriteTool creating a new file with content
    When: execute() is called
    Then: ToolResult includes content_metadata with operation, path, content_type, and metadata
    """
    # Create WriteTool with default config
    tool = WriteTool()

    # Write a new file
    test_file = tmp_path / "new_file.txt"
    result = tool.execute(path=str(test_file), content="Hello\nWorld\n")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "write"
    assert "new_file.txt" in result.content_metadata["path"]
    assert result.content_metadata["content_type"] == "summary"
    assert result.content_metadata["metadata"]["is_new_file"] is True
    assert result.content_metadata["metadata"]["lines"] == 2

  def test_content_metadata_for_overwrite(self, tmp_path: Path) -> None:
    """
    Given: WriteTool overwriting an existing file
    When: execute() is called
    Then: ToolResult includes content_metadata with is_overwrite=True
    """
    # Create WriteTool with overwrite allowed
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    tool = WriteTool(config=config)

    # Create existing file
    test_file = tmp_path / "existing.txt"
    test_file.write_text("Original content\n")

    # Overwrite the file
    result = tool.execute(path=str(test_file), content="New content\n")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["is_overwrite"] is True
    assert result.content_metadata["metadata"]["is_new_file"] is False

  def test_content_metadata_includes_content(self, tmp_path: Path) -> None:
    """
    Given: WriteTool with content display enabled
    When: execute() is called
    Then: content_metadata.content contains the written content
    """
    # Create WriteTool with verbosity="content"
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = WriteTool(config=config)

    # Write file
    test_file = tmp_path / "content.txt"
    result = tool.execute(path=str(test_file), content="Line 1\nLine 2\n")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "full"
    assert result.content_metadata["content"] == "Line 1\nLine 2\n"

  def test_content_metadata_omitted_when_disabled(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="silent"
    When: execute() is called
    Then: ToolResult.content_metadata is None
    """
    # Create WriteTool with silent verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="silent")
      )
    )
    tool = WriteTool(config=config)

    # Write file
    test_file = tmp_path / "silent.txt"
    result = tool.execute(path=str(test_file), content="Content\n")

    # Verify result
    assert result.success
    assert result.content_metadata is None


class TestWriteToolContentTruncation:
  """Test WriteTool content truncation for large files."""

  def test_truncation_for_large_files(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing content exceeding max_content_lines
    When: execute() is called
    Then: content_metadata.content is truncated
    """
    # Create WriteTool with small max_content_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          max_content_lines=5
        )
      )
    )
    tool = WriteTool(config=config)

    # Write file with 10 lines
    test_file = tmp_path / "large.txt"
    content = "\n".join(f"Line {i}" for i in range(10))
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "full"
    # Content should be truncated
    truncated_content = result.content_metadata["content"]
    assert truncated_content is not None
    assert truncated_content.count("\n") <= 5

  def test_truncation_metadata(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing large content that is truncated
    When: execute() is called
    Then: content_metadata.metadata includes truncated=True and original_line_count
    """
    # Create WriteTool with small max_content_lines
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          max_content_lines=5
        )
      )
    )
    tool = WriteTool(config=config)

    # Write file with 10 lines
    test_file = tmp_path / "truncated.txt"
    content = "\n".join(f"Line {i}" for i in range(10))
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"].get("truncated") is True
    assert result.content_metadata["metadata"].get("original_line_count") == 10

  def test_no_truncation_for_small_files(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing content within max_content_lines
    When: execute() is called
    Then: content_metadata.content contains full content
    """
    # Create WriteTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = WriteTool(config=config)

    # Write small file
    test_file = tmp_path / "small.txt"
    content = "Line 1\nLine 2\n"
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content"] == content
    assert result.content_metadata["metadata"].get("truncated") is None

  def test_truncation_respects_max_content_bytes(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing content exceeding max_content_bytes
    When: execute() is called
    Then: content_metadata.content is truncated to max_content_bytes
    """
    # Create WriteTool with small max_content_bytes
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          max_content_lines=1000,
          max_content_bytes=100
        )
      )
    )
    tool = WriteTool(config=config)

    # Write file with content > 100 bytes
    test_file = tmp_path / "large_bytes.txt"
    content = "x" * 200
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    truncated = result.content_metadata["content"]
    assert truncated is not None
    assert len(truncated) <= 100


class TestWriteToolEmptyFile:
  """Test WriteTool handling of empty files."""

  def test_empty_file_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing empty content
    When: execute() is called
    Then: content_metadata.metadata includes lines=0 and is_empty=True
    """
    # Create WriteTool
    tool = WriteTool()

    # Write empty file
    test_file = tmp_path / "empty.txt"
    result = tool.execute(path=str(test_file), content="")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["lines"] == 0
    assert result.content_metadata["metadata"]["is_empty"] is True

  def test_empty_file_summary_display(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing empty file with verbosity="summary"
    When: execute() is called
    Then: content_metadata shows summary (line count)
    """
    # Create WriteTool with summary verbosity
    tool = WriteTool()

    # Write empty file
    test_file = tmp_path / "empty_summary.txt"
    result = tool.execute(path=str(test_file), content="")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "summary"
    assert result.content_metadata["content"] is None


class TestWriteToolBinaryDetection:
  """Test WriteTool binary file detection."""

  def test_binary_file_detection(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing binary content
    When: execute() is called
    Then: content_metadata.content_type is "summary" (not "full")
    """
    # Create WriteTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = WriteTool(config=config)

    # Write binary content (contains null byte)
    test_file = tmp_path / "binary.bin"
    content = "Binary\x00content"
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "summary"
    assert result.content_metadata["metadata"]["is_binary"] is True

  def test_binary_file_metadata(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing binary content
    When: execute() is called
    Then: content_metadata.metadata includes is_binary=True and byte_size
    """
    # Create WriteTool
    tool = WriteTool()

    # Write binary content
    test_file = tmp_path / "binary_meta.bin"
    content = "Binary\x00data"
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["is_binary"] is True
    assert result.content_metadata["metadata"]["bytes"] == len(content)

  def test_binary_file_summary_only(self, tmp_path: Path) -> None:
    """
    Given: WriteTool writing binary content with verbosity="content"
    When: execute() is called
    Then: Only size summary is shown, not full content
    """
    # Create WriteTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = WriteTool(config=config)

    # Write binary content
    test_file = tmp_path / "binary_summary.bin"
    content = "Binary\x00content"
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    # Binary files always show summary, not content
    assert result.content_metadata["content"] is None


class TestWriteToolVerbosityLevels:
  """Test WriteTool behavior with different verbosity levels."""

  def test_silent_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="silent"
    When: WriteTool executes
    Then: ToolResult.content_metadata is None
    """
    # Create WriteTool with silent verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="silent")
      )
    )
    tool = WriteTool(config=config)

    # Write file
    test_file = tmp_path / "silent.txt"
    result = tool.execute(path=str(test_file), content="Content\n")

    # Verify result
    assert result.success
    assert result.content_metadata is None

  def test_summary_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="summary"
    When: WriteTool executes
    Then: content_metadata.content_type="summary" with line count
    """
    # Create WriteTool with summary verbosity (default)
    tool = WriteTool()

    # Write file
    test_file = tmp_path / "summary.txt"
    result = tool.execute(path=str(test_file), content="Line 1\nLine 2\nLine 3\n")

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "summary"
    assert result.content_metadata["content"] is None
    assert result.content_metadata["metadata"]["lines"] == 3

  def test_content_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="content"
    When: WriteTool executes
    Then: content_metadata.content_type="full" with full content
    """
    # Create WriteTool with content verbosity
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(verbosity="content")
      )
    )
    tool = WriteTool(config=config)

    # Write file
    test_file = tmp_path / "content.txt"
    content = "Line 1\nLine 2\n"
    result = tool.execute(path=str(test_file), content=content)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "full"
    assert result.content_metadata["content"] == content


class TestWriteToolConfigIntegration:
  """Test WriteTool integration with ContentDisplayConfig."""

  def test_write_tool_accesses_content_display_config(self) -> None:
    """
    Given: A Config with ContentDisplayConfig
    When: WriteTool accesses configuration
    Then: ContentDisplayConfig is available
    """
    # Create WriteTool with custom config
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          max_content_lines=100,
          show_diff_for_updates=True
        )
      )
    )
    tool = WriteTool(config=config)

    # Verify config is accessible
    assert tool._config.tools.content_display.verbosity == "content"
    assert tool._config.tools.content_display.max_content_lines == 100

  def test_write_tool_ignores_show_diff_for_updates(self, tmp_path: Path) -> None:
    """
    Given: WriteTool with show_diff_for_updates setting (irrelevant for write)
    When: Checking configuration
    Then: WriteTool ignores show_diff_for_updates (not applicable)
    """
    # Create WriteTool with show_diff_for_updates=False
    config = Config(
      tools=ToolsConfig(
        content_display=ContentDisplayConfig(
          verbosity="content",
          show_diff_for_updates=False
        )
      )
    )
    tool = WriteTool(config=config)

    # Write file - should still work (setting is ignored)
    test_file = tmp_path / "test.txt"
    result = tool.execute(path=str(test_file), content="Content\n")

    # Verify result - should show full content despite show_diff_for_updates=False
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "full"


class TestHelperFunctions:
  """Test helper functions."""

  def test_is_binary_detects_null_bytes(self) -> None:
    """
    Given: Content with null bytes
    When: _is_binary is called
    Then: Returns True
    """
    content = "Text\x00with\x00nulls"
    assert _is_binary(content) is True

  def test_is_binary_accepts_text(self) -> None:
    """
    Given: Plain text content
    When: _is_binary is called
    Then: Returns False
    """
    content = "Plain text\nwith newlines\nand no null bytes"
    assert _is_binary(content) is False

  def test_truncate_content_by_lines(self) -> None:
    """
    Given: Content with many lines
    When: _truncate_content is called with max_lines
    Then: Returns truncated content
    """
    content = "\n".join(f"Line {i}" for i in range(100))
    truncated, was_truncated, orig_lines, orig_bytes = _truncate_content(
      content, max_lines=10, max_bytes=10000
    )

    assert was_truncated is True
    assert orig_lines == 100
    # When truncating to max_lines, we get at most max_lines newlines
    assert truncated.count("\n") <= 10

  def test_truncate_content_by_bytes(self) -> None:
    """
    Given: Content with many bytes
    When: _truncate_content is called with max_bytes
    Then: Returns truncated content
    """
    content = "x" * 1000
    truncated, was_truncated, orig_lines, orig_bytes = _truncate_content(
      content, max_lines=1000, max_bytes=100
    )

    assert was_truncated is True
    assert len(truncated) <= 100
