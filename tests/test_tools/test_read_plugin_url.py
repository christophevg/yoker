"""Tests for read tool plugin:// URL support."""

import pytest

from yoker.builtin import read
from yoker.tools import ToolRegistry


def _read_spec():
  """Create and register the read tool."""
  registry = ToolRegistry()
  return registry.register(read)


class TestReadPluginUrl:
  """Tests for plugin:// URL handling in the read tool."""

  @pytest.mark.asyncio
  async def test_read_plugin_url_missing_package(self):
    """Test reading from non-existent package."""
    spec = _read_spec()

    result = await spec.execute(path="plugin://nonexistent_package/file.txt")

    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_plugin_url_invalid_format(self):
    """Test invalid plugin:// URL formats."""
    spec = _read_spec()

    # Missing path
    result = await spec.execute(path="plugin://package/")
    assert result.success is False
    assert "invalid" in result.error.lower()

    # Missing package
    result = await spec.execute(path="plugin:///path/to/file.txt")
    assert result.success is False
    assert "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_plugin_url_wrong_scheme(self):
    """Test URL with wrong scheme."""
    spec = _read_spec()

    # http:// should be rejected (not plugin://)
    result = await spec.execute(path="http://example.com/file.txt")

    # This should be treated as a regular file path, which will fail
    assert result.success is False
    # The error should be about file not found, not about plugin URL
    assert "not found" in result.error.lower() or "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_regular_file_still_works(self):
    """Test that regular file reading still works after plugin:// support."""
    import tempfile

    spec = _read_spec()

    # Create a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
      f.write("test content\n")
      temp_path = f.name

    try:
      result = await spec.execute(path=temp_path)
      assert result.success is True
      assert result.result == "test content\n"
    finally:
      import os

      os.unlink(temp_path)
