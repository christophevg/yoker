"""List tool implementation for Yoker.

Provides the ``make_list_tool`` factory that returns a callable for
listing directory contents. Guardrails are enforced centrally by the
harness based on the schema's ``path`` annotation.
"""

import fnmatch
from pathlib import Path
from typing import Annotated, Any

from structlog import get_logger

from yoker.annotations import Path as PathArg
from yoker.annotations import Text
from yoker.tools.base import ToolResult

log = get_logger(__name__)

DEFAULT_MAX_DEPTH: int = 1
DEFAULT_MAX_ENTRIES: int = 1000
ABSOLUTE_MAX_DEPTH: int = 10
ABSOLUTE_MAX_ENTRIES: int = 5000


def make_list_tool() -> Any:
  """Create the list tool callable."""

  async def list(
    path: Annotated[str, PathArg("Path to the directory to list")],
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    pattern: Annotated[str, Text('Optional glob pattern to filter entries (e.g., "*.py")')] = "",
  ) -> ToolResult:
    """List files and directories.

    Supports optional recursion, entry limits, and glob pattern filtering.
    """
    if not path:
      return ToolResult(success=False, error="Missing required parameter: path")

    try:
      max_depth = _clamp(int(max_depth), 0, ABSOLUTE_MAX_DEPTH)
      max_entries = _clamp(int(max_entries), 1, ABSOLUTE_MAX_ENTRIES)
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

      lines, file_count, dir_count, truncated = _build_tree(
        resolved, max_depth, max_entries, pattern
      )

      total = file_count + dir_count
      lines.append("")
      lines.append(f"{total} entries total ({file_count} files, {dir_count} directories)")
      if truncated:
        lines.append(f"... ({truncated} more entries truncated, max_entries={max_entries})")

      return ToolResult(success=True, result="\n".join(lines))
    except PermissionError:
      return ToolResult(success=False, error=f"Permission denied: {path}")
    except Exception as e:
      return ToolResult(success=False, error=f"Error listing directory: {e}")

  return list


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def _build_tree(
  root: Path,
  max_depth: int,
  max_entries: int,
  pattern: str,
) -> tuple[list[str], int, int, int]:
  """Build tree listing.

  Returns:
    Tuple of (lines, file_count, dir_count, truncated_count).
  """
  lines: list[str] = [str(root).rstrip("/") + "/"]
  file_count = 0
  dir_count = 0
  entry_count = 0
  truncated = 0

  if max_depth == 0:
    return lines, file_count, dir_count, truncated

  def walk(current: Path, depth: int, prefix: str = "") -> None:
    nonlocal file_count, dir_count, entry_count, truncated

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

      if entry.is_symlink():
        lines.append(prefix + entry.name)
        file_count += 1
        entry_count += 1
        continue

      if entry.is_dir():
        lines.append(prefix + entry.name + "/")
        dir_count += 1
        entry_count += 1
        walk(entry, depth + 1, prefix + "  ")
      else:
        lines.append(prefix + entry.name)
        file_count += 1
        entry_count += 1

  walk(root, 0)
  return lines, file_count, dir_count, truncated


__all__ = ["make_list_tool"]
