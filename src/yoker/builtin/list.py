"""List tool implementation for Yoker.

Provides the ``list`` async function for listing directory contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

from __future__ import annotations

import builtins
import fnmatch
from pathlib import Path
from typing import Annotated

from structlog import get_logger

from yoker.config import ListToolConfig
from yoker.tools.annotations import Path as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

ABSOLUTE_MAX_DEPTH: int = 10
ABSOLUTE_MAX_ENTRIES: int = 5000


# Keep function name as 'list' for backward compatibility with tool registry
# (Python allows 'list' as function name, shadowing the builtin)
async def list(
  path: Annotated[str, PathArg("Path to the directory to list")],
  ctx: ToolContext,
  max_depth: int | None = None,  # None means use config default
  max_entries: int | None = None,  # None means use config default
  pattern: Annotated[str, Text('Optional glob pattern to filter entries (e.g., "*.py")')] = "",
) -> ToolResult:
  """List files and directories.

  Supports optional recursion, entry limits, and glob pattern filtering.
  Configuration defaults come from ctx.config (ListToolConfig).

  Args:
    path: Path to the directory to list.
    ctx: Tool execution context with configuration.
    max_depth: Maximum directory depth (None = use config default, 0 = root only).
    max_entries: Maximum entries to return (None = use config default).
    pattern: Optional glob pattern to filter entries.

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
    effective_max_depth = _clamp(int(effective_max_depth), 0, ABSOLUTE_MAX_DEPTH)
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

    lines, file_count, dir_count, truncated = _build_tree(
      resolved, effective_max_depth, effective_max_entries, pattern
    )

    total = file_count + dir_count
    lines.append("")
    lines.append(f"{total} entries total ({file_count} files, {dir_count} directories)")
    if truncated:
      lines.append(f"... ({truncated} more entries truncated, max_entries={effective_max_entries})")

    return ToolResult(success=True, result="\n".join(lines))
  except PermissionError:
    return ToolResult(success=False, error=f"Permission denied: {path}")
  except Exception as e:
    return ToolResult(success=False, error=f"Error listing directory: {e}")


def _clamp(value: int, minimum: int, maximum: int) -> int:
  """Clamp a value to a range."""
  return max(minimum, min(value, maximum))


def _build_tree(
  root: Path,
  max_depth: int,
  max_entries: int,
  pattern: str,
) -> tuple[builtins.list[str], int, int, int]:
  """Build tree listing.

  Returns:
    Tuple of (lines, file_count, dir_count, truncated_count).
  """
  lines: builtins.list[str] = [str(root).rstrip("/") + "/"]
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


# Export as 'list' for the tool name
__all__ = ["list"]
