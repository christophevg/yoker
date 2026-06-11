"""Tests for content_type module."""

from pathlib import Path

from yoker.content_type import _detect_from_extension, detect_content_type


class TestDetectContentType:
  """Tests for detect_content_type function."""

  def test_detect_markdown_extension(self) -> None:
    """Test detection from .md extension."""
    path = Path("README.md")
    content = b"# Heading\n\nContent"
    result = detect_content_type(content, path)
    assert result == "text/markdown"

  def test_detect_html_extension(self) -> None:
    """Test detection from .html extension."""
    path = Path("index.html")
    content = b"<html><body>Content</body></html>"
    result = detect_content_type(content, path)
    assert result == "text/html"

  def test_detect_json_extension(self) -> None:
    """Test detection from .json extension."""
    path = Path("config.json")
    content = b'{"key": "value"}'
    result = detect_content_type(content, path)
    assert result == "application/json"

  def test_detect_diff_extension(self) -> None:
    """Test detection from .diff extension."""
    path = Path("changes.diff")
    content = b"--- a/file.txt\n+++ b/file.txt\n@@ -1,1 +1,1 @@\n-old\n+new"
    result = detect_content_type(content, path)
    assert result == "text/x-diff"

  def test_detect_python_extension_fallback(self) -> None:
    """Test that Python files fall back to text/plain."""
    path = Path("script.py")
    content = b"print('hello')"
    result = detect_content_type(content, path)
    assert result == "text/plain"

  def test_detect_unknown_extension_fallback(self) -> None:
    """Test fallback to text/plain for unknown extensions."""
    path = Path("file.xyz")
    content = b"some content"
    result = detect_content_type(content, path)
    assert result == "text/plain"

  def test_detect_no_extension_fallback(self) -> None:
    """Test fallback for files without extension."""
    path = Path("README")
    content = b"some content"
    result = detect_content_type(content, path)
    assert result == "text/plain"


class TestDetectFromExtension:
  """Tests for _detect_from_extension function."""

  def test_markdown_extensions(self) -> None:
    """Test Markdown extensions."""
    assert _detect_from_extension(Path("file.md")) == "text/markdown"
    assert _detect_from_extension(Path("file.markdown")) == "text/markdown"

  def test_html_extensions(self) -> None:
    """Test HTML extensions."""
    assert _detect_from_extension(Path("file.html")) == "text/html"
    assert _detect_from_extension(Path("file.htm")) == "text/html"

  def test_json_extension(self) -> None:
    """Test JSON extension."""
    assert _detect_from_extension(Path("file.json")) == "application/json"

  def test_yaml_extensions(self) -> None:
    """Test YAML extensions."""
    assert _detect_from_extension(Path("file.yaml")) == "text/yaml"
    assert _detect_from_extension(Path("file.yml")) == "text/yaml"

  def test_diff_extensions(self) -> None:
    """Test diff extensions."""
    assert _detect_from_extension(Path("file.diff")) == "text/x-diff"
    assert _detect_from_extension(Path("file.patch")) == "text/x-diff"

  def test_code_extensions(self) -> None:
    """Test code file extensions (should return text/plain)."""
    assert _detect_from_extension(Path("file.py")) == "text/plain"
    assert _detect_from_extension(Path("file.js")) == "text/plain"
    assert _detect_from_extension(Path("file.ts")) == "text/plain"
    assert _detect_from_extension(Path("file.rs")) == "text/plain"
    assert _detect_from_extension(Path("file.go")) == "text/plain"

  def test_unknown_extension(self) -> None:
    """Test unknown extension returns None."""
    assert _detect_from_extension(Path("file.xyz")) is None
    assert _detect_from_extension(Path("file.unknown")) is None

  def test_no_extension(self) -> None:
    """Test file without extension returns None."""
    assert _detect_from_extension(Path("README")) is None

  def test_case_insensitive(self) -> None:
    """Test that extension matching is case-insensitive."""
    assert _detect_from_extension(Path("file.MD")) == "text/markdown"
    assert _detect_from_extension(Path("file.HTML")) == "text/html"
    assert _detect_from_extension(Path("file.JSON")) == "application/json"

