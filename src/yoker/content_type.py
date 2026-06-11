"""Content type detection utility for Yoker.

Provides content type detection from file content and path extension.
Used by tools to set appropriate content_type in ToolContentEvent.
"""

from pathlib import Path


def detect_content_type(content: bytes, path: Path) -> str:
  """Detect the MIME content type of file content.

  Detection strategy:
    1. Try library detection (python-magic if available)
    2. Fallback: Detect from file extension
    3. Fallback: Default to "text/plain"

  Args:
    content: Raw file content as bytes.
    path: Path to the file (used for extension-based fallback).

  Returns:
    MIME content type string (e.g., "text/plain", "text/x-diff").
  """
  # Strategy 1: Try library detection
  mime_type = _detect_with_library(content)
  if mime_type:
    return mime_type

  # Strategy 2: Fallback to extension-based detection
  mime_type = _detect_from_extension(path)
  if mime_type:
    return mime_type

  # Strategy 3: Default to plain text
  return "text/plain"


def _detect_with_library(content: bytes) -> str | None:
  """Try to detect content type using python-magic library.

  Args:
    content: Raw file content as bytes.

  Returns:
    MIME type if detection succeeds and is text/*, None otherwise.
  """
  try:
    import magic  # type: ignore[import-not-found]

    mime = magic.from_buffer(content, mime=True)
    # Only return if it's a text type (to avoid binary types)
    if mime and mime.startswith("text/"):
      return str(mime)
    return None
  except ImportError:
    # python-magic not available
    return None


def _detect_from_extension(path: Path) -> str | None:
  """Detect content type from file extension.

  Args:
    path: Path to the file.

  Returns:
    MIME type if extension is recognized, None otherwise.
  """
  # Extension to MIME type mapping
  # Note: This is a simplified mapping; many extensions map to text/plain
  extension_map: dict[str, str] = {
    # Markup languages
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "text/xml",
    # Data formats
    ".json": "application/json",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".toml": "text/toml",
    # Diff/patch formats
    ".diff": "text/x-diff",
    ".patch": "text/x-diff",
    # Code (treated as text/plain with potential syntax highlighting)
    ".py": "text/plain",
    ".js": "text/plain",
    ".ts": "text/plain",
    ".java": "text/plain",
    ".c": "text/plain",
    ".cpp": "text/plain",
    ".h": "text/plain",
    ".rs": "text/plain",
    ".go": "text/plain",
    ".rb": "text/plain",
    ".php": "text/plain",
    ".sh": "text/plain",
    ".bash": "text/plain",
    ".zsh": "text/plain",
    ".ps1": "text/plain",
    # Config files
    ".cfg": "text/plain",
    ".conf": "text/plain",
    ".config": "text/plain",
    ".ini": "text/plain",
    # Documentation
    ".txt": "text/plain",
    ".rst": "text/plain",
    ".adoc": "text/plain",
  }

  ext = path.suffix.lower()
  return extension_map.get(ext)


__all__ = ["detect_content_type"]
