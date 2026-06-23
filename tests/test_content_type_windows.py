"""Tests for Windows-specific content_type issues.

This module tests edge cases where python-magic may be installed but misconfigured,
causing exceptions beyond ImportError (e.g., OSError, RuntimeError on Windows).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestDetectContentTypeFallback:
  """Tests for fallback behavior when library detection fails.

  These tests simulate various failure modes of python-magic to ensure
  the content type detection gracefully falls back to extension-based detection.
  """

  def test_detect_with_library_handles_import_error(self) -> None:
    """Test that _detect_with_library handles ImportError (magic not installed)."""
    from yoker.tools.content_type import _detect_with_library

    # Mock the magic module to not exist
    with patch.dict("sys.modules", {"magic": None}):
      # When magic is not available, should return None
      result = _detect_with_library(b"test content")
      assert result is None

  def test_detect_with_library_handles_os_error(self) -> None:
    """Test that _detect_with_library handles OSError (DLL missing on Windows)."""
    from yoker.tools.content_type import _detect_with_library

    # Mock magic module that raises OSError when used
    mock_magic = MagicMock()
    mock_magic.from_buffer.side_effect = OSError("libmagic DLL not found")

    with patch.dict("sys.modules", {"magic": mock_magic}):
      # Should catch OSError and return None
      result = _detect_with_library(b"test content")
      assert result is None

  def test_detect_with_library_handles_runtime_error(self) -> None:
    """Test that _detect_with_library handles RuntimeError (libmagic invalid state)."""
    from yoker.tools.content_type import _detect_with_library

    mock_magic = MagicMock()
    mock_magic.from_buffer.side_effect = RuntimeError("libmagic initialization failed")

    with patch.dict("sys.modules", {"magic": mock_magic}):
      result = _detect_with_library(b"test content")
      assert result is None

  def test_detect_with_library_handles_any_exception(self) -> None:
    """Test that _detect_with_library handles any exception from magic."""
    from yoker.tools.content_type import _detect_with_library

    mock_magic = MagicMock()
    mock_magic.from_buffer.side_effect = Exception("Unknown error")

    with patch.dict("sys.modules", {"magic": mock_magic}):
      result = _detect_with_library(b"test content")
      assert result is None

  def test_detect_content_type_falls_back_on_magic_error(self) -> None:
    """Test that detect_content_type falls back to extension when magic fails.

    This is the critical test that was hanging on Windows. When _detect_with_library
    encounters any exception, the function should fall back to extension detection.
    """
    from yoker.tools.content_type import detect_content_type

    # Mock magic module that raises OSError (Windows DLL issue)
    mock_magic = MagicMock()
    mock_magic.from_buffer.side_effect = OSError("libmagic DLL not found")

    with patch.dict("sys.modules", {"magic": mock_magic}):
      path = Path("README.md")
      content = b"# Heading\n\nContent"

      # Should fall back to extension-based detection
      result = detect_content_type(content, path)
      assert result == "text/markdown"

  def test_detect_content_type_with_various_magic_failures(self) -> None:
    """Test extension fallback works with different magic failures."""
    from yoker.tools.content_type import detect_content_type

    test_cases = [
      (Path("README.md"), b"# Test", "text/markdown"),
      (Path("index.html"), b"<html>", "text/html"),
      (Path("config.json"), b'{"key": "value"}', "application/json"),
      (Path("changes.diff"), b"--- a/file.txt", "text/x-diff"),
      (Path("script.py"), b"print('hello')", "text/plain"),
    ]

    for path, content, expected in test_cases:
      mock_magic = MagicMock()
      mock_magic.from_buffer.side_effect = RuntimeError("libmagic error")

      with patch.dict("sys.modules", {"magic": mock_magic}):
        result = detect_content_type(content, path)
        assert result == expected, f"Failed for {path}: expected {expected}, got {result}"
