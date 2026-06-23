"""Tests for write tool content metadata emission.

Task: 1.5.5 - Show Write/Update Tool Content in CLI
"""

from pathlib import Path

import pytest

from yoker.builtin import write
from yoker.builtin.write import _is_binary, _truncate_content
from yoker.config import (
  Config,
  ContentDisplayConfig,
  ToolsConfig,
  ToolsSharedConfig,
  WriteToolConfig,
)
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext


def _write_spec():
  """Create and register the write tool."""
  registry = ToolRegistry()
  return registry.register(write, name="write")


def _get_ctx(config: Config | None = None) -> ToolContext:
  """Get ToolContext for tests that need config."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.write,
    shared=config.tools_shared,
    backends={},
  )


class TestWriteToolContentMetadataEmission:
  """Test write tool content metadata emission."""

  @pytest.mark.asyncio
  async def test_content_metadata_for_new_file(self, tmp_path: Path) -> None:
    """
    Given: write tool creating a new file with content
    When: execute() is called
    Then: ToolResult includes content_metadata with operation, path, content_type, and metadata
    """
    spec = _write_spec()

    # Write a new file
    test_file = tmp_path / "new_file.txt"
    result = await spec.execute(path=str(test_file), content="Hello\nWorld\n", ctx=_get_ctx())

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["operation"] == "write"
    assert "new_file.txt" in result.content_metadata["path"]
    assert result.content_metadata["content_type"] == "application/x-summary"
    assert result.content_metadata["metadata"]["is_new_file"] is True
    assert result.content_metadata["metadata"]["lines"] == 2

  @pytest.mark.asyncio
  async def test_content_metadata_for_overwrite(self, tmp_path: Path) -> None:
    """
    Given: write tool overwriting an existing file
    When: execute() is called
    Then: ToolResult includes content_metadata with is_overwrite=True
    """
    # Create write tool with overwrite allowed
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Create existing file
    test_file = tmp_path / "existing.txt"
    test_file.write_text("Original content\n")

    # Overwrite the file
    result = await spec.execute(path=str(test_file), content="New content\n", ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["is_overwrite"] is True
    assert result.content_metadata["metadata"]["is_new_file"] is False

  @pytest.mark.asyncio
  async def test_content_metadata_includes_content(self, tmp_path: Path) -> None:
    """
    Given: write tool with content display enabled
    When: execute() is called
    Then: content_metadata.content contains the written content
    """
    # Create write tool with verbosity="content"
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="content")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file
    test_file = tmp_path / "content.txt"
    result = await spec.execute(path=str(test_file), content="Line 1\nLine 2\n", ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/plain"
    assert result.content_metadata["content"] == "Line 1\nLine 2\n"

  @pytest.mark.asyncio
  async def test_content_metadata_omitted_when_disabled(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="silent"
    When: execute() is called
    Then: ToolResult.content_metadata is None
    """
    # Create write tool with silent verbosity
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="silent")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file
    test_file = tmp_path / "silent.txt"
    result = await spec.execute(path=str(test_file), content="Content\n", ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is None


class TestWriteToolContentTruncation:
  """Test write tool content truncation for large files."""

  @pytest.mark.asyncio
  async def test_truncation_for_large_files(self, tmp_path: Path) -> None:
    """
    Given: write tool writing content exceeding max_content_lines
    When: execute() is called
    Then: content_metadata.content is truncated
    """
    # Create write tool with small max_content_lines
    config = Config(
      tools_shared=ToolsSharedConfig(
        content_display=ContentDisplayConfig(verbosity="content", max_content_lines=5)
      )
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file with 10 lines
    test_file = tmp_path / "large.txt"
    content = "\n".join(f"Line {i}" for i in range(10))
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/plain"
    # Content should be truncated
    truncated_content = result.content_metadata["content"]
    assert truncated_content is not None
    assert truncated_content.count("\n") <= 5

  @pytest.mark.asyncio
  async def test_truncation_metadata(self, tmp_path: Path) -> None:
    """
    Given: write tool writing large content that is truncated
    When: execute() is called
    Then: content_metadata.metadata includes truncated=True and original_line_count
    """
    # Create write tool with small max_content_lines
    config = Config(
      tools_shared=ToolsSharedConfig(
        content_display=ContentDisplayConfig(verbosity="content", max_content_lines=5)
      )
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file with 10 lines
    test_file = tmp_path / "truncated.txt"
    content = "\n".join(f"Line {i}" for i in range(10))
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"].get("truncated") is True
    assert result.content_metadata["metadata"].get("original_line_count") == 10

  @pytest.mark.asyncio
  async def test_no_truncation_for_small_files(self, tmp_path: Path) -> None:
    """
    Given: write tool writing content within max_content_lines
    When: execute() is called
    Then: content_metadata.content contains full content
    """
    # Create write tool with content verbosity
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="content")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write small file
    test_file = tmp_path / "small.txt"
    content = "Line 1\nLine 2\n"
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content"] == content
    assert result.content_metadata["metadata"].get("truncated") is None

  @pytest.mark.asyncio
  async def test_truncation_respects_max_content_bytes(self, tmp_path: Path) -> None:
    """
    Given: write tool writing content exceeding max_content_bytes
    When: execute() is called
    Then: content_metadata.content is truncated to max_content_bytes
    """
    # Create write tool with small max_content_bytes
    config = Config(
      tools_shared=ToolsSharedConfig(
        content_display=ContentDisplayConfig(
          verbosity="content", max_content_lines=1000, max_content_bytes=100
        )
      )
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file with content > 100 bytes
    test_file = tmp_path / "large_bytes.txt"
    content = "x" * 200
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    truncated = result.content_metadata["content"]
    assert truncated is not None
    assert len(truncated) <= 100


class TestWriteToolEmptyFile:
  """Test write tool handling of empty files."""

  @pytest.mark.asyncio
  async def test_empty_file_content_metadata(self, tmp_path: Path) -> None:
    """
    Given: write tool writing empty content
    When: execute() is called
    Then: content_metadata.metadata includes lines=0 and is_empty=True
    """
    # Create write tool
    spec = _write_spec()

    # Write empty file
    test_file = tmp_path / "empty.txt"
    result = await spec.execute(path=str(test_file), content="", ctx=_get_ctx())

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["lines"] == 0
    assert result.content_metadata["metadata"]["is_empty"] is True

  @pytest.mark.asyncio
  async def test_empty_file_summary_display(self, tmp_path: Path) -> None:
    """
    Given: write tool writing empty file with verbosity="summary"
    When: execute() is called
    Then: content_metadata shows summary (line count)
    """
    # Create write tool with summary verbosity
    spec = _write_spec()

    # Write empty file
    test_file = tmp_path / "empty_summary.txt"
    result = await spec.execute(path=str(test_file), content="", ctx=_get_ctx())

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "application/x-summary"
    assert result.content_metadata["content"] is None


class TestWriteToolBinaryDetection:
  """Test write tool binary file detection."""

  @pytest.mark.asyncio
  async def test_binary_file_detection(self, tmp_path: Path) -> None:
    """
    Given: write tool writing binary content
    When: execute() is called
    Then: content_metadata.content_type == "application/x-summary" (not "full")
    """
    # Create write tool with content verbosity
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="content")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write binary content (contains null byte)
    test_file = tmp_path / "binary.bin"
    content = "Binary\x00content"
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "application/x-summary"
    assert result.content_metadata["metadata"]["is_binary"] is True

  @pytest.mark.asyncio
  async def test_binary_file_metadata(self, tmp_path: Path) -> None:
    """
    Given: write tool writing binary content
    When: execute() is called
    Then: content_metadata.metadata includes is_binary=True and byte_size
    """
    # Create write tool
    spec = _write_spec()

    # Write binary content
    test_file = tmp_path / "binary_meta.bin"
    content = "Binary\x00data"
    result = await spec.execute(path=str(test_file), content=content, ctx=_get_ctx())

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["metadata"]["is_binary"] is True
    assert result.content_metadata["metadata"]["bytes"] == len(content)

  @pytest.mark.asyncio
  async def test_binary_file_summary_only(self, tmp_path: Path) -> None:
    """
    Given: write tool writing binary content with verbosity="content"
    When: execute() is called
    Then: Only size summary is shown, not full content
    """
    # Create write tool with content verbosity
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="content")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write binary content
    test_file = tmp_path / "binary_summary.bin"
    content = "Binary\x00content"
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    # Binary files always show summary, not content
    assert result.content_metadata["content"] is None


class TestWriteToolVerbosityLevels:
  """Test write tool behavior with different verbosity levels."""

  @pytest.mark.asyncio
  async def test_silent_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="silent"
    When: write tool executes
    Then: ToolResult.content_metadata is None
    """
    # Create write tool with silent verbosity
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="silent")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file
    test_file = tmp_path / "silent.txt"
    result = await spec.execute(path=str(test_file), content="Content\n", ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is None

  @pytest.mark.asyncio
  async def test_summary_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="summary"
    When: write tool executes
    Then: content_metadata.content_type == "application/x-summary" with line count
    """
    # Create write tool with summary verbosity (default)
    spec = _write_spec()

    # Write file
    test_file = tmp_path / "summary.txt"
    result = await spec.execute(
      path=str(test_file), content="Line 1\nLine 2\nLine 3\n", ctx=_get_ctx()
    )

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "application/x-summary"
    assert result.content_metadata["content"] is None
    assert result.content_metadata["metadata"]["lines"] == 3

  @pytest.mark.asyncio
  async def test_content_verbosity(self, tmp_path: Path) -> None:
    """
    Given: ContentDisplayConfig with verbosity="content"
    When: write tool executes
    Then: content_metadata.content_type="full" with full content
    """
    # Create write tool with content verbosity
    config = Config(
      tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="content")),
    )
    spec = _write_spec()
    ctx = _get_ctx(config)

    # Write file
    test_file = tmp_path / "content.txt"
    content = "Line 1\nLine 2\n"
    result = await spec.execute(path=str(test_file), content=content, ctx=ctx)

    # Verify result
    assert result.success
    assert result.content_metadata is not None
    assert result.content_metadata["content_type"] == "text/plain"
    assert result.content_metadata["content"] == content


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
