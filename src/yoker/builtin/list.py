"""List tool implementation for Yoker.

Provides the ``list`` async function for listing directory contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.

The ``blocked_path_patterns`` from ``ToolContext`` are checked internally
for every file/directory traversed, preventing bypass via list showing
files that would be blocked by the guardrail.
"""

from __future__ import annotations

import builtins
import fnmatch
from pathlib import Path
from typing import Annotated, Any

from structlog import get_logger

from yoker.config import ListToolConfig
from yoker.tools.annotations import ReadPath, Text
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import is_path_blocked
from yoker.tools.ignore import IgnoreMatcher
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

ABSOLUTE_MAX_DEPTH: int = 10
ABSOLUTE_MAX_ENTRIES: int = 5000


# Keep function name as 'list' for backward compatibility with tool registry
# (Python allows 'list' as function name, shadowing the builtin)
async def list(
  path: Annotated[str, ReadPath("Path to the directory to list")],
  ctx: ToolContext,
  max_depth: int | None = None,  # None means use config default
  max_entries: int | None = None,  # None means use config default
  pattern: Annotated[str, Text('Optional glob pattern to filter entries (e.g., "*.py")')] = "",
  include_ignored: bool = False,
) -> ToolResult:
  """List files and directories.

  Supports optional recursion, entry limits, and glob pattern filtering.
  Configuration defaults come from ctx.config (ListToolConfig).
  Files/directories matching ignore patterns (.gitignore, skip_dirs,
  dotfiles) are excluded by default. Use include_ignored=True to show them.

  Args:
    path: Path to the directory to list.
    ctx: Tool execution context with configuration.
    max_depth: Maximum directory depth (None = use config default, 1 = root only).
    max_entries: Maximum entries to return (None = use config default).
    pattern: Optional glob pattern to filter entries.
    include_ignored: Include files/directories that match ignore patterns
      (.gitignore, skip_dirs, dotfiles). Default False.

  Returns:
    ToolResult with directory listing.
  """
  if not path:
    return ToolResult(success=False, error="Missing required parameter: path")

  config = ctx.config
  if not isinstance(config, ListToolConfig):
    logger.warning("list_invalid_config_type", config_type=type(config).__name__)
    return ToolResult(success=False, error="Invalid configuration for list tool")
  default_max_depth = config.max_depth
  default_max_entries = config.max_entries

  # Use provided values or config defaults
  effective_max_depth = max_depth if max_depth is not None else default_max_depth
  effective_max_entries = max_entries if max_entries is not None else default_max_entries

  try:
    effective_max_depth = _clamp(int(effective_max_depth), 1, ABSOLUTE_MAX_DEPTH)
    effective_max_entries = _clamp(int(effective_max_entries), 1, ABSOLUTE_MAX_ENTRIES)
  except (ValueError, TypeError):
    return ToolResult(success=False, error="Invalid numeric parameter")

  if pattern is None:
    pattern = ""

  try:
    resolved = Path(path)
    if not resolved.exists():
      return ToolResult(success=False, error=f"Path not found: {path}")

    if not resolved.is_dir():
      return ToolResult(
        success=True,
        result=f"{resolved.name}\n\n1 entry total (1 file, 0 directories)",
      )

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

    lines, file_count, dir_count, truncated, hidden = _build_tree(
      resolved, effective_max_depth, effective_max_entries, pattern, matcher, blocked_patterns
    )

    total = file_count + dir_count
    lines.append("")
    lines.append(f"{total} entries total ({file_count} files, {dir_count} directories)")
    if hidden > 0:
      # #61: a bare "0 entries" reads as absence. Report what the ignore
      # rules suppressed so the caller can tell "empty" from "hidden".
      lines.append(
        f"{hidden} entries hidden by ignore rules (use include_ignored=true to show them)"
      )
    if truncated:
      lines.append(f"... ({truncated} more entries truncated, max_entries={effective_max_entries})")

    content = "\n".join(lines)
    content_metadata = {
      "operation": "list",
      "path": str(resolved),
      "content_type": "text/plain",
      "content": content,
      "metadata": {
        "total_entries": total,
        "file_count": file_count,
        "dir_count": dir_count,
        "hidden_entries": hidden,
        "truncated": truncated,
        "max_depth": effective_max_depth,
        "max_entries": effective_max_entries,
      },
    }
    return ToolResult(success=True, result=content, content_metadata=content_metadata)
  except PermissionError:
    return ToolResult(success=False, error=f"Permission denied: {path}")
  except Exception as e:
    logger.error("list_error", error=str(e))
    return ToolResult(success=False, error=f"Error listing directory: {e}")


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def _build_tree(
  root: Path,
  max_depth: int,
  max_entries: int,
  pattern: str,
  matcher: IgnoreMatcher | None = None,
  blocked_patterns: builtins.list[Any] | None = None,
) -> tuple[builtins.list[str], int, int, int, int]:
  """Build tree listing.

  Returns:
    Tuple of (lines, file_count, dir_count, truncated_count, hidden_count).
    ``hidden_count`` is the number of entries excluded by ignore rules
    (gitignore patterns, skip_dirs, dotfiles) — reported so the caller can
    distinguish "empty" from "hidden" (#61). Blocked-path suppression is
    a separate enforcement mechanism and is NOT counted.
  """
  lines: builtins.list[str] = [str(root).rstrip("/") + "/"]
  file_count = 0
  dir_count = 0
  entry_count = 0
  truncated = 0
  hidden = 0

  def walk(current: Path, depth: int, prefix: str = "") -> None:
    nonlocal file_count, dir_count, entry_count, truncated, hidden

    if depth >= max_depth or entry_count >= max_entries:
      return

    try:
      entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
      lines.append(prefix + "... (permission denied)")
      return

    if pattern:
      entries = [e for e in entries if fnmatch.fnmatch(e.name, pattern)]

    for entry in entries:
      if entry_count >= max_entries:
        truncated += 1
        continue

      is_dir = entry.is_dir() and not entry.is_symlink()

      # Apply ignore filtering
      if matcher is not None:
        if matcher.should_ignore_path(entry, is_dir=is_dir):
          hidden += 1
          continue

      # Apply blocked_paths enforcement
      if blocked_patterns and is_path_blocked(entry, root, blocked_patterns):
        continue

      if entry.is_symlink():
        lines.append(prefix + entry.name)
        file_count += 1
        entry_count += 1
        continue

      if is_dir:
        lines.append(prefix + entry.name + "/")
        dir_count += 1
        entry_count += 1
        walk(entry, depth + 1, prefix + "  ")
      else:
        lines.append(prefix + entry.name)
        file_count += 1
        entry_count += 1

  walk(root, 0)
  return lines, file_count, dir_count, truncated, hidden


# Export as 'list' for the tool name
__all__ = ["list"]
