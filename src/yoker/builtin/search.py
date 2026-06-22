"""Search tool implementation for Yoker.

Provides the ``search`` async function for searching files and their contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

import fnmatch
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.annotations import Path as PathArg
from yoker.annotations import Text
from yoker.tools.base import ToolResult
from yoker.tools.context import ToolContext

if TYPE_CHECKING:
  from yoker.config import SearchToolConfig

log = get_logger(__name__)

ABSOLUTE_MAX_RESULTS: int = 1000
MAX_FILE_SIZE_KB: int = 500
MAX_PATTERN_LENGTH: int = 500
ABSOLUTE_TIMEOUT_MS: int = 30000

FORBIDDEN_PATTERNS: tuple[str, ...] = (
  r"\([^)]*[+*][^)]*\)[+*]",
  r"\([^)]*\|[^)]*\)[+*]",
)

SKIP_DIRS: frozenset[str] = frozenset(
  {
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
  }
)


async def search(
  path: Annotated[str, PathArg("Directory to search in")],
  ctx: ToolContext,
  pattern: Annotated[
    str,
    Text(
      "Search pattern. For 'content' type: regex pattern. "
      "For 'filename' type: glob pattern (e.g., '*.py')"
    ),
  ] = "",
  type: str = "content",
  max_results: int | None = None,  # None means use config default
  timeout_ms: int | None = None,  # None means use config default
) -> ToolResult:
  """Search for patterns in files.

  Args:
    path: Directory to search in.
    ctx: Tool execution context with configuration.
    pattern: Search pattern (regex for content, glob for filename).
    type: Search type - 'content' or 'filename'.
    max_results: Maximum results to return (None = use config default).
    timeout_ms: Search timeout in milliseconds (None = use config default).

  Returns:
    ToolResult with search results.
  """
  if not path:
    return ToolResult(success=False, error="Missing required parameter: path")

  config: "SearchToolConfig" = ctx.config
  default_max_results = config.max_results
  default_timeout_ms = config.timeout_ms

  # Use provided values or config defaults
  effective_max_results = max_results if max_results is not None else default_max_results
  effective_timeout_ms = timeout_ms if timeout_ms is not None else default_timeout_ms

  try:
    effective_max_results = _clamp(int(effective_max_results), 1, ABSOLUTE_MAX_RESULTS)
    effective_timeout_ms = _clamp(int(effective_timeout_ms), 100, ABSOLUTE_TIMEOUT_MS)
  except (ValueError, TypeError):
    return ToolResult(success=False, error="Invalid numeric parameter")

  search_type = type
  if search_type not in ("content", "filename"):
    return ToolResult(
      success=False,
      error=f"Invalid type: {search_type}. Must be 'content' or 'filename'",
    )

  search_pattern = pattern
  if not search_pattern:
    search_pattern = "*" if search_type == "filename" else ".*"

  if search_type == "content":
    is_valid, error = _validate_regex(search_pattern)
    if not is_valid:
      return ToolResult(success=False, error=error)

  try:
    resolved = Path(path)
    if not resolved.exists():
      return ToolResult(success=False, error=f"Path not found: {path}")
    if not resolved.is_dir():
      return ToolResult(success=False, error=f"Path is not a directory: {path}")
  except PermissionError:
    return ToolResult(success=False, error=f"Permission denied: {path}")
  except Exception as e:
    return ToolResult(success=False, error=f"Invalid path: {e}")

  try:
    if search_type == "content":
      matches, total, truncated, files_searched = _search_content(
        resolved, search_pattern, effective_max_results, effective_timeout_ms
      )
      result = {
        "success": True,
        "matches": matches,
        "total_matches": total,
        "truncated": truncated,
        "files_searched": files_searched,
      }
    else:
      matches, total, truncated = _search_filename(resolved, search_pattern, effective_max_results)
      result = {
        "success": True,
        "matches": matches,
        "total_matches": total,
        "truncated": truncated,
      }

    log.info(
      "search_success",
      path=str(resolved),
      type=search_type,
      pattern=search_pattern,
      total_matches=total,
      files_searched=result.get("files_searched"),
    )
    return ToolResult(success=True, result=result)
  except PermissionError:
    return ToolResult(success=False, error=f"Permission denied: {path}")
  except Exception as e:
    log.error("search_error", error=str(e))
    return ToolResult(success=False, error=f"Error searching: {e}")


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def _validate_regex(pattern: str) -> tuple[bool, str]:
  """Validate regex pattern for safety."""
  if len(pattern) > MAX_PATTERN_LENGTH:
    return False, f"Pattern too long: max {MAX_PATTERN_LENGTH} characters"

  for forbidden in FORBIDDEN_PATTERNS:
    if re.search(forbidden, pattern):
      return False, "Pattern rejected: potential ReDoS vulnerability (nested quantifiers)"

  try:
    re.compile(pattern)
    return True, ""
  except re.error as e:
    return False, f"Invalid regex pattern: {e}"


def _walk_files(root: Path) -> Iterator[Path]:
  """Walk directory tree, yielding files."""
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]

    for filename in filenames:
      if filename.startswith("."):
        continue
      file_path = Path(dirpath) / filename
      yield file_path


def _search_content(
  root: Path,
  pattern: str,
  max_results: int,
  timeout_ms: int,
) -> tuple[list[dict[str, Any]], int, bool, int]:
  """Search file contents using regex."""
  matches: list[dict[str, Any]] = []
  total_count = 0
  truncated = False
  files_searched = 0

  regex = re.compile(pattern)
  max_size = MAX_FILE_SIZE_KB * 1024
  start_time = time.monotonic()
  timeout_seconds = timeout_ms / 1000.0

  for file_path in _walk_files(root):
    if time.monotonic() - start_time > timeout_seconds:
      truncated = True
      break

    files_searched += 1

    try:
      if file_path.is_symlink():
        continue
      if file_path.stat().st_size > max_size:
        continue

      content = file_path.read_text(encoding="utf-8", errors="replace")
      for line_num, line in enumerate(content.splitlines(), 1):
        if regex.search(line):
          total_count += 1
          if len(matches) < max_results:
            matches.append(
              {
                "file": str(file_path),
                "line": line_num,
                "content": line.strip(),
              }
            )
    except (UnicodeDecodeError, PermissionError, OSError):
      continue

  if len(matches) < total_count:
    truncated = True

  return matches, total_count, truncated, files_searched


def _search_filename(
  root: Path,
  pattern: str,
  max_results: int,
) -> tuple[list[dict[str, Any]], int, bool]:
  """Search file names using glob pattern."""
  matches: list[dict[str, Any]] = []
  total_count = 0
  truncated = False

  for file_path in _walk_files(root):
    if fnmatch.fnmatch(file_path.name, pattern):
      total_count += 1
      if len(matches) < max_results:
        matches.append({"file": str(file_path)})

  if len(matches) < total_count:
    truncated = True

  return matches, total_count, truncated


__all__ = ["search"]
