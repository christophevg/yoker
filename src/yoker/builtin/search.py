"""Search tool implementation for Yoker.

Provides the ``search`` async function for searching files and their contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

import builtins
import fnmatch
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from structlog import get_logger

from yoker.config import SearchToolConfig
from yoker.tools.annotations import Path as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

ABSOLUTE_MAX_RESULTS: int = 1000
MAX_FILE_SIZE_KB: int = 500
MAX_PATTERN_LENGTH: int = 500
ABSOLUTE_TIMEOUT_MS: int = 30000
MAX_CONTEXT_LINES: int = 20
CAT_N_WIDTH = 6

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
  case_insensitive: bool = False,
  context_before: int = 0,
  context_after: int = 0,
  include_pattern: str = "",
  exclude_pattern: str = "",
  count_only: bool = False,
) -> ToolResult:
  """Search for patterns in files.

  Args:
    path: Directory to search in.
    ctx: Tool execution context with configuration.
    pattern: Search pattern (regex for content, glob for filename).
    type: Search type - 'content' or 'filename'.
    max_results: Maximum results to return (None = use config default).
    timeout_ms: Search timeout in milliseconds (None = use config default).
    case_insensitive: Case-insensitive regex/filename matching.
    context_before: Lines of context before each match (content search only, capped at 20).
    context_after: Lines of context after each match (content search only, capped at 20).
    include_pattern: Glob filter for files to search (empty = no filter).
    exclude_pattern: Glob filter for files to skip (empty = no filter).
    count_only: Return per-file counts only, no matched content (content search only).

  Returns:
    ToolResult with search results. When any enhanced parameter is non-default,
    a flat ``content_metadata`` dict is attached for grep-style UI rendering.
  """
  if not path:
    return ToolResult(success=False, error="Missing required parameter: path")

  config = ctx.config
  if not isinstance(config, SearchToolConfig):
    logger.warning("search_invalid_config_type", config_type=builtins.type(config).__name__)
    return ToolResult(success=False, error="Invalid configuration for search tool")
  default_max_results = config.max_results
  default_timeout_ms = config.timeout_ms

  # Use provided values or config defaults
  effective_max_results = max_results if max_results is not None else default_max_results
  effective_timeout_ms = timeout_ms if timeout_ms is not None else default_timeout_ms

  try:
    effective_max_results = _clamp(int(effective_max_results), 1, ABSOLUTE_MAX_RESULTS)
    effective_timeout_ms = _clamp(int(effective_timeout_ms), 100, ABSOLUTE_TIMEOUT_MS)
    effective_context_before = _clamp(int(context_before), 0, MAX_CONTEXT_LINES)
    effective_context_after = _clamp(int(context_after), 0, MAX_CONTEXT_LINES)
  except (ValueError, TypeError):
    return ToolResult(success=False, error="Invalid numeric parameter")

  effective_case_insensitive = bool(case_insensitive)
  effective_count_only = bool(count_only)

  for p in (include_pattern, exclude_pattern):
    if len(p) > MAX_PATTERN_LENGTH:
      return ToolResult(
        success=False, error=f"Pattern too long: max {MAX_PATTERN_LENGTH} characters"
      )

  if effective_count_only and (effective_context_before or effective_context_after):
    logger.warning("search_count_only_with_context_ignored")

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

  enhanced = (
    effective_case_insensitive
    or effective_context_before > 0
    or effective_context_after > 0
    or bool(include_pattern)
    or bool(exclude_pattern)
    or effective_count_only
  )

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
      matches, total, truncated, files_searched, counts = _search_content(
        resolved,
        search_pattern,
        effective_max_results,
        effective_timeout_ms,
        case_insensitive=effective_case_insensitive,
        context_before=effective_context_before,
        context_after=effective_context_after,
        include_pattern=include_pattern,
        exclude_pattern=exclude_pattern,
        count_only=effective_count_only,
      )
      if effective_count_only:
        result = {
          "success": True,
          "counts": counts,
          "total_matches": total,
          "truncated": truncated,
          "files_searched": files_searched,
        }
      else:
        result = {
          "success": True,
          "matches": matches,
          "total_matches": total,
          "truncated": truncated,
          "files_searched": files_searched,
        }
    else:
      matches, total, truncated = _search_filename(
        resolved,
        search_pattern,
        effective_max_results,
        case_insensitive=effective_case_insensitive,
        include_pattern=include_pattern,
        exclude_pattern=exclude_pattern,
      )
      result = {
        "success": True,
        "matches": matches,
        "total_matches": total,
        "truncated": truncated,
      }

    logger.info(
      "search_success",
      path=str(resolved),
      type=search_type,
      pattern=search_pattern,
      total_matches=total,
      files_searched=result.get("files_searched"),
    )

    if enhanced:
      content_metadata = _build_search_content_metadata(
        resolved=resolved,
        search_type=search_type,
        result=result,
        case_insensitive=effective_case_insensitive,
        context_before=effective_context_before,
        context_after=effective_context_after,
        include_pattern=include_pattern,
        exclude_pattern=exclude_pattern,
        count_only=effective_count_only,
      )
      return ToolResult(success=True, result=result, content_metadata=content_metadata)
    return ToolResult(success=True, result=result)
  except PermissionError:
    return ToolResult(success=False, error=f"Permission denied: {path}")
  except Exception as e:
    logger.error("search_error", error=str(e))
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


def _walk_files(
  root: Path,
  include_pattern: str = "",
  exclude_pattern: str = "",
) -> Iterator[Path]:
  """Walk directory tree, yielding files, applying optional glob filters on filename."""
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]

    for filename in filenames:
      if filename.startswith("."):
        continue
      if include_pattern and not fnmatch.fnmatchcase(filename, include_pattern):
        continue
      if exclude_pattern and fnmatch.fnmatchcase(filename, exclude_pattern):
        continue
      file_path = Path(dirpath) / filename
      yield file_path


def _render_context_lines(lines: list[str], start_idx: int, count: int) -> list[str]:
  """Render up to ``count`` lines starting at 0-indexed ``start_idx`` as cat -n strings.

  ``start_idx`` is clamped to file boundaries; fewer lines are returned at edges.
  """
  if count <= 0:
    return []
  end = max(start_idx, min(len(lines), start_idx + count))
  slice_lines = lines[start_idx:end]
  return [f"{start_idx + j + 1:>{CAT_N_WIDTH}}\t{line}" for j, line in enumerate(slice_lines)]


def _search_content(
  root: Path,
  pattern: str,
  max_results: int,
  timeout_ms: int,
  case_insensitive: bool = False,
  context_before: int = 0,
  context_after: int = 0,
  include_pattern: str = "",
  exclude_pattern: str = "",
  count_only: bool = False,
) -> tuple[list[dict[str, Any]], int, bool, int, dict[str, int]]:
  """Search file contents using regex."""
  matches: list[dict[str, Any]] = []
  counts: dict[str, int] = {}
  total_count = 0
  truncated = False
  files_searched = 0

  flags = re.IGNORECASE if case_insensitive else 0
  regex = re.compile(pattern, flags)
  max_size = MAX_FILE_SIZE_KB * 1024
  start_time = time.monotonic()
  timeout_seconds = timeout_ms / 1000.0
  collect_context = (context_before > 0 or context_after > 0) and not count_only

  for file_path in _walk_files(root, include_pattern, exclude_pattern):
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
      lines = content.splitlines()
      file_str = str(file_path)
      file_count = 0
      for line_num, line in enumerate(lines, 1):
        if regex.search(line):
          total_count += 1
          file_count += 1
          if count_only:
            continue
          if len(matches) < max_results:
            match: dict[str, Any] = {
              "file": file_str,
              "line": line_num,
              "content": line.strip(),
            }
            if collect_context:
              match_idx = line_num - 1
              before_start = max(0, match_idx - context_before)
              before_count = match_idx - before_start
              match["context_before"] = _render_context_lines(lines, before_start, before_count)
              match["context_after"] = _render_context_lines(lines, match_idx + 1, context_after)
            matches.append(match)
      if count_only and file_count > 0:
        counts[file_str] = file_count
    except (UnicodeDecodeError, PermissionError, OSError):
      continue

  if not count_only and len(matches) < total_count:
    truncated = True

  return matches, total_count, truncated, files_searched, counts


def _search_filename(
  root: Path,
  pattern: str,
  max_results: int,
  case_insensitive: bool = False,
  include_pattern: str = "",
  exclude_pattern: str = "",
) -> tuple[list[dict[str, Any]], int, bool]:
  """Search file names using glob pattern."""
  matches: list[dict[str, Any]] = []
  total_count = 0
  truncated = False

  pattern_lower = pattern.lower() if case_insensitive else None

  for file_path in _walk_files(root, include_pattern, exclude_pattern):
    name = file_path.name
    if pattern_lower is not None:
      matched = fnmatch.fnmatch(name.lower(), pattern_lower)
    else:
      matched = fnmatch.fnmatchcase(name, pattern)
    if matched:
      total_count += 1
      if len(matches) < max_results:
        matches.append({"file": str(file_path)})

  if len(matches) < total_count:
    truncated = True

  return matches, total_count, truncated


def _parse_cat_n(s: str) -> tuple[int, str]:
  """Split a cat -n style string ``"   123\ttext"`` into (line_num, text)."""
  parts = s.split("\t", 1)
  num = int(parts[0].strip())
  text = parts[1] if len(parts) > 1 else ""
  return num, text


def _render_search_text(
  search_type: str,
  result: dict[str, Any],
  count_only: bool,
) -> str:
  """Render search results as grep-style text for content_metadata.content."""
  if search_type == "filename":
    return "\n".join(m["file"] for m in result.get("matches", []))
  if count_only:
    counts = result.get("counts", {})
    return "\n".join(f"{file}:{count}" for file, count in counts.items())
  lines: list[str] = []
  for m in result.get("matches", []):
    file = m["file"]
    line_num = m["line"]
    content = m["content"]
    for ctx in m.get("context_before", []):
      ctx_num, ctx_text = _parse_cat_n(ctx)
      lines.append(f"{file}-{ctx_num}-{ctx_text}")
    lines.append(f"{file}:{line_num}:{content}")
    for ctx in m.get("context_after", []):
      ctx_num, ctx_text = _parse_cat_n(ctx)
      lines.append(f"{file}-{ctx_num}-{ctx_text}")
  return "\n".join(lines)


def _build_search_content_metadata(
  resolved: Path,
  search_type: str,
  result: dict[str, Any],
  case_insensitive: bool,
  context_before: int,
  context_after: int,
  include_pattern: str,
  exclude_pattern: str,
  count_only: bool,
) -> dict[str, Any]:
  """Build the flat content_metadata dict consumed by ToolContentEvent."""
  return {
    "operation": "search",
    "path": str(resolved),
    "content_type": "text/plain",
    "content": _render_search_text(search_type, result, count_only),
    "metadata": {
      "case_insensitive": case_insensitive,
      "context_before": context_before,
      "context_after": context_after,
      "include_pattern": include_pattern,
      "exclude_pattern": exclude_pattern,
      "count_only": count_only,
      "total_matches": result.get("total_matches", 0),
    },
  }


__all__ = ["search"]
