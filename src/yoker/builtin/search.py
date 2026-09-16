"""Search tool implementation for Yoker.

Provides the ``search`` async function for searching files and their contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.

The ``blocked_path_patterns`` from ``ToolContext`` are checked internally
for every file traversed, preventing bypass via search reading content
of files that would be blocked by the guardrail.
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
from yoker.tools.annotations import ReadPath, Text
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import is_path_blocked
from yoker.tools.ignore import IgnoreMatcher
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

# Fallback skip dirs when no IgnoreMatcher is provided (backward compat)
_FALLBACK_SKIP_DIRS: frozenset[str] = frozenset(
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
  }
)

# T5 (agent feedback): binary junk floor for CONTENT search. These are
# excluded even with include_ignored=True — cache/db noise (e.g.
# .mypy_cache/**/*.db) once returned ~14 junk "matches" hiding 2 real
# ones. Directory names are matched as any path segment; extensions by
# suffix. include_binaries=True opts back in; filename search is never
# affected.
_BINARY_FLOOR_DIRS: frozenset[str] = frozenset(
  {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
  }
)

_BINARY_FLOOR_SUFFIXES: frozenset[str] = frozenset(
  {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".obj",
    ".whl",
    ".tar",
    ".gz",
    ".zip",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".icns",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".class",
    ".jar",
  }
)


async def search(
  path: Annotated[
    str,
    ReadPath(
      "Directory or file to search in. Can be a directory (recursively searches all files) "
      "or a single file path (searches just that file)."
    ),
  ],
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
  include_ignored: bool = False,
  include_binaries: bool = False,
) -> ToolResult:
  """Search for patterns in files.

  The 'path' parameter can be a directory (recursively searches all files) or a
  single file (searches just that file).

  Args:
    path: Directory or file to search in.
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
    include_ignored: Include files/directories that match ignore patterns
      (.gitignore, skip_dirs, dotfiles). Default False.
    include_binaries: Opt back into binary-junk files for CONTENT search
      (cache dirs like .mypy_cache/.venv and binary extensions like .db,
      .pyc, .so, images, archives). The binary floor is a safety net that
      stays active even with include_ignored=True; this flag is the only
      way through. Filename search is never affected by the floor.

  Returns:
    ToolResult with search results. When any enhanced parameter is non-default,
    a flat ``content_metadata`` dict is attached for grep-style UI rendering.
    Content-search results suppressed by the binary floor are counted in
    ``hidden_by_ignore`` (T5), so a zero-result stays explainable.
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
    if not resolved.is_dir() and not resolved.is_file():
      return ToolResult(
        success=False,
        error=f"Path is neither a file nor a directory: {path}",
      )
  except PermissionError:
    return ToolResult(success=False, error=f"Permission denied: {path}")
  except Exception as e:
    return ToolResult(success=False, error=f"Invalid path: {e}")

  # Build ignore matcher from shared config
  ignore_cfg = ctx.shared.ignore if ctx.shared else None
  try:
    if include_ignored or ignore_cfg is None:
      matcher = IgnoreMatcher(
        resolved,
        ignore_files=(),
        skip_dirs=(),
        skip_dotfiles=False,
        respect_ignore_files=False,
      )
    else:
      matcher = IgnoreMatcher(
        resolved,
        ignore_files=ignore_cfg.ignore_files,
        skip_dirs=ignore_cfg.skip_dirs,
        skip_dotfiles=ignore_cfg.skip_dotfiles,
        respect_ignore_files=ignore_cfg.respect_ignore_files,
      )
  except (PermissionError, OSError):
    matcher = None

  # Get blocked_path patterns for internal enforcement
  blocked_patterns = ctx.blocked_path_patterns if ctx else []

  # T5 (agent feedback): binary-junk floor for CONTENT search only.
  # Cache dirs and binary extensions are excluded even with
  # include_ignored=True (that flag once dragged .mypy_cache/**/*.db
  # noise into results); include_binaries=True is the explicit opt-in.
  # A single-file target is never filtered — the caller chose that file.
  effective_include_binaries = bool(include_binaries)
  binary_floor = search_type == "content" and not effective_include_binaries and resolved.is_dir()

  try:
    hidden_skips: list[int] = [0]
    floor_skips: list[int] = [0]
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
        matcher=matcher,
        blocked_patterns=blocked_patterns,
        skip_counter=hidden_skips,
        binary_floor=binary_floor,
        floor_counter=floor_skips,
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
        matcher=matcher,
        blocked_patterns=blocked_patterns,
        skip_counter=hidden_skips,
      )
      result = {
        "success": True,
        "matches": matches,
        "total_matches": total,
        "truncated": truncated,
      }

    # #61: report visibility. A bare "no matches" reads as absence; when
    # ignore rules suppressed entries, say so and hint at include_ignored.
    # T5: floor suppressions are counted separately so the zero-result
    # hint names the right remedy — include_binaries lifts the floor,
    # include_ignored does not.
    hidden = hidden_skips[0]
    floor_hidden = floor_skips[0]
    total_hidden = hidden + floor_hidden
    if total_hidden > 0:
      result["hidden_by_ignore"] = total_hidden
      if total == 0:
        if floor_hidden > 0 and hidden == 0:
          # Only the floor suppressed entries: name its remedy.
          result["hint"] = (
            f"{floor_hidden} binary/cache file(s) were hidden by the binary floor — "
            "retry with include_binaries=true if the target is a cache/binary file "
            "(include_ignored alone will not lift the binary floor)"
          )
        elif hidden > 0 and floor_hidden == 0:
          result["hint"] = (
            f"{hidden} file(s)/dir(s) were hidden by ignore rules — "
            "retry with include_ignored=true if the target may be ignored"
          )
        else:
          result["hint"] = (
            f"{hidden} file(s)/dir(s) were hidden by ignore rules and "
            f"{floor_hidden} binary/cache file(s) by the binary floor — "
            "retry with include_ignored=true and/or include_binaries=true"
          )

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


def _is_binary_floor_hit(
  file_path: Path,
) -> bool:
  """T5: does this path fall under the binary-junk floor?

  Matches when any path segment is a known cache/dependency directory OR
  the filename carries a binary junk suffix. Called for content search
  only (the floor is disabled for filename search and single-file
  targets).
  """
  parts = file_path.parts
  for part in parts:
    if part in _BINARY_FLOOR_DIRS:
      return True
  return file_path.suffix.lower() in _BINARY_FLOOR_SUFFIXES


def _walk_files(
  root: Path,
  include_pattern: str = "",
  exclude_pattern: str = "",
  matcher: IgnoreMatcher | None = None,
  blocked_patterns: list[Any] | None = None,
  skip_counter: list[int] | None = None,
  binary_floor: bool = False,
  floor_counter: list[int] | None = None,
) -> Iterator[Path]:
  """Walk directory tree, yielding files, applying optional glob filters on filename.

  If ``root`` is a file (not a directory), yields just that file (ignoring
  include/exclude patterns, since the caller explicitly chose this file).
  When ``matcher`` is provided, directories and files matching ignore
  patterns are pruned. When ``blocked_patterns`` is provided, files
  matching blocked_path glob patterns are skipped (internal enforcement of
  the universal denylist).

  When ``skip_counter`` is a list, the number of entries suppressed by
  ignore rules (gitignore patterns, skip_dirs, dotfiles) is appended to
  it — reported so the caller can distinguish "no matches" from "no
  matches because everything is hidden" (#61). Blocked-path suppression
  is a separate enforcement mechanism and is NOT counted.

  T5: when ``binary_floor`` is True, binary-junk files (cache dirs,
  binary extensions) are pruned from CONTENT search even with
  ``include_ignored=True``; their count goes to ``floor_counter`` (kept
  separate from ignore-rule suppressions so the zero-result hint can name
  the right remedy). Floor suppressions ARE reported in
  ``hidden_by_ignore`` (they reduce visibility just the same).
  """
  if root.is_file():
    # Even single files must pass the blocked check
    if blocked_patterns and is_path_blocked(root, root.parent, blocked_patterns):
      return
    yield root
    return

  for dirpath, dirnames, filenames in os.walk(root):
    if matcher is not None:
      # Prune ignored directories in-place, counting what is pruned (#61)
      kept: list[str] = []
      for d in dirnames:
        if matcher.should_skip_dir(d) or matcher.should_ignore_path(Path(dirpath) / d, is_dir=True):
          if skip_counter is not None:
            skip_counter[0] += 1
          continue
        kept.append(d)
      dirnames[:] = kept
    else:
      dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _FALLBACK_SKIP_DIRS]

    # Also prune blocked directories
    if blocked_patterns:
      dirnames[:] = [
        d for d in dirnames if not is_path_blocked(Path(dirpath) / d, root, blocked_patterns)
      ]

    # T5: prune floor directories here (in-place, before file iteration)
    # so the whole subtree is skipped, not just files inside it. Only
    # count dirs that are NOT also ignored by the matcher — an ignored
    # dir is already counted by the matcher branch above; counting it
    # twice would inflate hidden_by_ignore and misattribute the remedy.
    if binary_floor:
      ignored_names: set[str] = set()
      if matcher is not None:
        for d in dirnames:
          if matcher.should_skip_dir(d) or matcher.should_ignore_path(
            Path(dirpath) / d, is_dir=True
          ):
            ignored_names.add(d)
      kept_floor: list[str] = []
      for d in dirnames:
        if d in ignored_names:
          continue
        if d in _BINARY_FLOOR_DIRS:
          if floor_counter is not None:
            floor_counter[0] += 1
          continue
        kept_floor.append(d)
      dirnames[:] = kept_floor

    for filename in filenames:
      if matcher is not None:
        file_path = Path(dirpath) / filename
        if matcher.should_ignore_path(file_path, is_dir=False):
          if skip_counter is not None:
            skip_counter[0] += 1
          continue
      else:
        if filename.startswith("."):
          if skip_counter is not None:
            skip_counter[0] += 1
          continue
      if include_pattern and not fnmatch.fnmatchcase(filename, include_pattern):
        continue
      if exclude_pattern and fnmatch.fnmatchcase(filename, exclude_pattern):
        continue
      file_path = Path(dirpath) / filename
      # T5: binary-junk floor — prune BEFORE the blocked check (the floor
      # is a visibility concern, not a security one; counting keeps a
      # zero-result explainable). Floor suppressions go to their own
      # counter so the caller can distinguish them from ignore-rule
      # suppressions when choosing the hint.
      if binary_floor and _is_binary_floor_hit(file_path):
        if floor_counter is not None:
          floor_counter[0] += 1
        continue
      # Internal enforcement of blocked_paths
      if blocked_patterns and is_path_blocked(file_path, root, blocked_patterns):
        continue
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
  matcher: IgnoreMatcher | None = None,
  blocked_patterns: list[Any] | None = None,
  skip_counter: list[int] | None = None,
  binary_floor: bool = False,
  floor_counter: list[int] | None = None,
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

  for file_path in _walk_files(
    root,
    include_pattern,
    exclude_pattern,
    matcher=matcher,
    blocked_patterns=blocked_patterns,
    skip_counter=skip_counter,
    binary_floor=binary_floor,
    floor_counter=floor_counter,
  ):
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
      file_str = file_path.as_posix()
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
  matcher: IgnoreMatcher | None = None,
  blocked_patterns: list[Any] | None = None,
  skip_counter: list[int] | None = None,
) -> tuple[list[dict[str, Any]], int, bool]:
  """Search file names using glob pattern."""
  matches: list[dict[str, Any]] = []
  total_count = 0
  truncated = False

  pattern_lower = pattern.lower() if case_insensitive else None

  for file_path in _walk_files(
    root,
    include_pattern,
    exclude_pattern,
    matcher=matcher,
    blocked_patterns=blocked_patterns,
    skip_counter=skip_counter,
  ):
    name = file_path.name
    if pattern_lower is not None:
      matched = fnmatch.fnmatch(name.lower(), pattern_lower)
    else:
      matched = fnmatch.fnmatchcase(name, pattern)
    if matched:
      total_count += 1
      if len(matches) < max_results:
        matches.append({"file": file_path.as_posix()})

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
