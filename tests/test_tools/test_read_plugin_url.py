"""Tests for ReadTool plugin:// URL support."""

import pytest

from yoker.tools.read import ReadTool


class TestReadPluginUrl:
  """Tests for plugin:// URL handling in ReadTool."""

  @pytest.mark.asyncio
  async def test_read_plugin_url_missing_package(self):
    """Test reading from non-existent package."""
    tool = ReadTool()

    result = await tool.execute(path="plugin://nonexistent_package/file.txt")

    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_plugin_url_invalid_format(self):
    """Test invalid plugin:// URL formats."""
    tool = ReadTool()

    # Missing path
    result = await tool.execute(path="plugin://package/")
    assert result.success is False
    assert "invalid" in result.error.lower()

    # Missing package
    result = await tool.execute(path="plugin:///path/to/file.txt")
    assert result.success is False
    assert "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_plugin_url_wrong_scheme(self):
    """Test URL with wrong scheme."""
    tool = ReadTool()

    # http:// should be rejected (not plugin://)
    result = await tool.execute(path="http://example.com/file.txt")

    # This should be treated as a regular file path, which will fail
    assert result.success is False
    # The error should be about file not found, not about plugin URL
    assert "not found" in result.error.lower() or "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_regular_file_still_works(self):
    """Test that regular file reading still works after plugin:// support."""
    import tempfile

    tool = ReadTool()

    # Create a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
      f.write("test content\n")
      temp_path = f.name

    try:
      result = await tool.execute(path=temp_path)
      assert result.success is True
      assert result.result == "test content\n"
    finally:
      import os

      os.unlink(temp_path)
