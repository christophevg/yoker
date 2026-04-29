"""Search tool implementation for Yoker.

Provides the SearchTool for searching files and their contents with
regex patterns (content search) and glob patterns (filename search).
"""

import fnmatch
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class SearchTool(Tool):
  """Tool for searching files and their contents.

  Supports two search modes:
  - 'content': Search within file contents (grep-like, using regex)
  - 'filename': Search file names (glob-like, using fnmatch)

  All searches respect allowed paths guardrails and enforce limits
  to prevent resource exhaustion.

  ReDoS Prevention:
  - Pattern length limit (500 characters)
  - Forbidden pattern detection (nested quantifiers)
  - Compile-time regex validation
  - File size filtering (skip large files)
  """

  # Operational limits
  DEFAULT_MAX_RESULTS: int = 100
  ABSOLUTE_MAX_RESULTS: int = 1000
  MAX_FILE_SIZE_KB: int = 500
  MAX_PATTERN_LENGTH: int = 500

  # Timeout limits (in milliseconds)
  DEFAULT_TIMEOUT_MS: int = 5000
  ABSOLUTE_TIMEOUT_MS: int = 30000

  # Forbidden regex patterns that cause ReDoS
  # These patterns match dangerous constructs in user-provided regex
  FORBIDDEN_PATTERNS: tuple[str, ...] = (
    # Nested quantifiers: (a+)+, (a*)*, (a+)*, etc.
    r"\([^)]*[+*][^)]*\)[+*]",
    # Alternation with nested quantifiers
    r"\([^)]*\|[^)]*\)[+*]",
  )

  # Directories to skip during search
  SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    "htmlcov",
    ".tox",
    ".eggs",
    "*.egg-info",
  })

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize SearchTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "search"

  @property
  def description(self) -> str:
    return (
      "Search for patterns in files. "
      "Use type='content' for grep-like regex search in file contents. "
      "Use type='filename' for find-like glob pattern matching."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the search tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Directory to search in",
            },
            "pattern": {
              "type": "string",
              "description": (
                "Search pattern. For 'content' type: regex pattern. "
                "For 'filename' type: glob pattern (e.g., '*.py')"
              ),
            },
            "type": {
              "type": "string",
              "enum": ["content", "filename"],
              "description": (
                "Type of search: 'content' searches within files, "
                "'filename' searches file names. Defaults to 'content'."
              ),
            },
            "max_results": {
              "type": "integer",
              "description": (
                f"Maximum results to return. Defaults to {self.DEFAULT_MAX_RESULTS}."
              ),
              "minimum": 1,
              "maximum": self.ABSOLUTE_MAX_RESULTS,
            },
            "timeout_ms": {
              "type": "integer",
              "description": (
                f"Maximum search time in milliseconds. Defaults to {self.DEFAULT_TIMEOUT_MS}."
              ),
              "minimum": 100,
              "maximum": self.ABSOLUTE_TIMEOUT_MS,
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Search files with pattern matching and limits.

    Args:
      **kwargs: Must contain 'path'. May contain 'pattern', 'type',
        and 'max_results'.

    Returns:
      ToolResult with search results or error message.
    """
    path_str = kwargs.get("path", "")
    if not path_str:
      return ToolResult(
        success=False,
        result="",
        error="Missing required parameter: path",
      )

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "search_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Parse and clamp parameters
    try:
      max_results = self._clamp(
        int(kwargs.get("max_results", self.DEFAULT_MAX_RESULTS)),
        1,
        self.ABSOLUTE_MAX_RESULTS,
      )
    except (ValueError, TypeError):
      return ToolResult(
        success=False,
        result="",
        error="Invalid numeric parameter: max_results",
      )

    try:
      timeout_ms = self._clamp(
        int(kwargs.get("timeout_ms", self.DEFAULT_TIMEOUT_MS)),
        100,
        self.ABSOLUTE_TIMEOUT_MS,
      )
    except (ValueError, TypeError):
      return ToolResult(
        success=False,
        result="",
        error="Invalid numeric parameter: timeout_ms",
      )

    search_type = kwargs.get("type", "content")
    if search_type not in ("content", "filename"):
      return ToolResult(
        success=False,
        result="",
        error=f"Invalid type: {search_type}. Must be 'content' or 'filename'",
      )

    pattern = kwargs.get("pattern", "")
    if not pattern:
      pattern = "*" if search_type == "filename" else ".*"

    # Validate regex for content search
    if search_type == "content":
      is_valid, error = self._validate_regex(pattern)
      if not is_valid:
        return ToolResult(success=False, result="", error=error)

    # Validate path
    try:
      path = Path(path_str)
      if not path.exists():
        return ToolResult(
          success=False,
          result="",
          error=f"Path not found: {path_str}",
        )
      if not path.is_dir():
        return ToolResult(
          success=False,
          result="",
          error=f"Path is not a directory: {path_str}",
        )
    except PermissionError:
      return ToolResult(success=False, result="", error=f"Permission denied: {path_str}")
    except Exception as e:
      return ToolResult(success=False, result="", error=f"Invalid path: {e}")

    # Execute search
    try:
      if search_type == "content":
        matches, total, truncated, files_searched = self._search_content(
          path, pattern, max_results, timeout_ms
        )
        result = {
          "success": True,
          "matches": matches,
          "total_matches": total,
          "truncated": truncated,
          "files_searched": files_searched,
        }
      else:
        matches, total, truncated = self._search_filename(path, pattern, max_results)
        result = {
          "success": True,
          "matches": matches,
          "total_matches": total,
          "truncated": truncated,
        }

      log.info(
        "search_success",
        path=str(path),
        type=search_type,
        pattern=pattern,
        total_matches=total,
        files_searched=result.get("files_searched"),
      )

      return ToolResult(success=True, result=result)

    except PermissionError:
      return ToolResult(success=False, result="", error=f"Permission denied: {path_str}")
    except Exception as e:
      log.error("search_error", error=str(e))
      return ToolResult(success=False, result="", error=f"Error searching: {e}")

  def _clamp(self, value: int, minimum: int, maximum: int) -> int:
    """Clamp a value to a range.

    Args:
      value: Value to clamp.
      minimum: Minimum value.
      maximum: Maximum value.

    Returns:
      Clamped value.
    """
    return max(minimum, min(value, maximum))

  def _validate_regex(self, pattern: str) -> tuple[bool, str]:
    """Validate regex pattern for safety.

    Checks for:
    - Maximum pattern length
    - Dangerous constructs (nested quantifiers)
    - Compile-time regex validity

    Args:
      pattern: Regex pattern to validate.

    Returns:
      Tuple of (is_valid, error_message).
    """
    # Length check
    if len(pattern) > self.MAX_PATTERN_LENGTH:
      return False, f"Pattern too long: max {self.MAX_PATTERN_LENGTH} characters"

    # Check for forbidden patterns (ReDoS vectors)
    for forbidden in self.FORBIDDEN_PATTERNS:
      if re.search(forbidden, pattern):
        return (
          False,
          "Pattern rejected: potential ReDoS vulnerability (nested quantifiers)",
        )

    # Try to compile the pattern
    try:
      re.compile(pattern)
      return True, ""
    except re.error as e:
      return False, f"Invalid regex pattern: {e}"

  def _walk_files(self, root: Path) -> Iterator[Path]:
    """Walk directory tree, yielding files.

    Skips:
    - Hidden files/directories (starting with .)
    - Common binary directories (.git, __pycache__, node_modules, etc.)
    - Symlinks

    Args:
      root: Root directory to walk.

    Yields:
      Path objects for each file found.
    """
    for dirpath, dirnames, filenames in os.walk(root):
      # Skip hidden and binary directories
      dirnames[:] = [
        d for d in dirnames if not d.startswith(".") and d not in self.SKIP_DIRS
      ]

      for filename in filenames:
        # Skip hidden files
        if filename.startswith("."):
          continue

        file_path = Path(dirpath) / filename

        # Skip symlinks
        if file_path.is_symlink():
          continue

        yield file_path

  def _search_content(
    self,
    root: Path,
    pattern: str,
    max_results: int,
    timeout_ms: int,
  ) -> tuple[list[dict[str, Any]], int, bool, int]:
    """Search file contents using regex.

    Args:
      root: Root directory to search.
      pattern: Regex pattern to match.
      max_results: Maximum results to return.
      timeout_ms: Maximum search time in milliseconds.

    Returns:
      Tuple of (matches, total_count, truncated, files_searched).
    """
    matches: list[dict[str, Any]] = []
    total_count = 0
    truncated = False
    files_searched = 0

    # Compile regex (already validated)
    regex = re.compile(pattern)
    max_size = self.MAX_FILE_SIZE_KB * 1024

    # Track timeout
    start_time = time.monotonic()
    timeout_seconds = timeout_ms / 1000.0

    for file_path in self._walk_files(root):
      # Check timeout periodically (on each file iteration)
      if time.monotonic() - start_time > timeout_seconds:
        truncated = True
        break

      files_searched += 1

      try:
        # Skip large files
        if file_path.stat().st_size > max_size:
          continue

        # Read file content
        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Search each line
        for line_num, line in enumerate(content.splitlines(), 1):
          if regex.search(line):
            total_count += 1
            if len(matches) < max_results:
              matches.append({
                "file": str(file_path),
                "line": line_num,
                "content": line.strip(),
              })

      except (UnicodeDecodeError, PermissionError, OSError):
        # Skip binary files and permission-denied files
        continue

    if len(matches) < total_count:
      truncated = True

    return matches, total_count, truncated, files_searched

  def _search_filename(
    self,
    root: Path,
    pattern: str,
    max_results: int,
  ) -> tuple[list[dict[str, Any]], int, bool]:
    """Search file names using glob pattern.

    Args:
      root: Root directory to search.
      pattern: Glob pattern to match.
      max_results: Maximum results to return.

    Returns:
      Tuple of (matches, total_count, truncated).
    """
    matches: list[dict[str, Any]] = []
    total_count = 0
    truncated = False

    for file_path in self._walk_files(root):
      if fnmatch.fnmatch(file_path.name, pattern):
        total_count += 1
        if len(matches) < max_results:
          matches.append({"file": str(file_path)})

    if len(matches) < total_count:
      truncated = True

    return matches, total_count, truncated