"""List tool implementation for Yoker.

Provides the ListTool for listing directory contents with configurable
depth, entry limits, and glob pattern filtering.
"""

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger

from .base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class ListTool(Tool):
  """Tool for listing directory contents.

  Lists files and directories with optional recursion depth control,
  entry limits, and glob pattern filtering. Returns a tree-formatted
  string for LLM consumption.

  When a guardrail is provided, validates parameters before listing.
  """

  DEFAULT_MAX_DEPTH: int = 1
  DEFAULT_MAX_ENTRIES: int = 1000
  ABSOLUTE_MAX_DEPTH: int = 10
  ABSOLUTE_MAX_ENTRIES: int = 5000

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize ListTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "list"

  @property
  def description(self) -> str:
    return (
      "List files and directories. "
      "Supports optional recursion (max_depth), "
      "entry limits (max_entries), and glob pattern filtering."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the list tool."""
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
              "description": "Path to the directory to list",
            },
            "max_depth": {
              "type": "integer",
              "description": (
                "Maximum recursion depth (1 = immediate children only). "
                f"Defaults to {self.DEFAULT_MAX_DEPTH}."
              ),
              "minimum": 0,
              "maximum": self.ABSOLUTE_MAX_DEPTH,
            },
            "max_entries": {
              "type": "integer",
              "description": (
                "Maximum total entries to return. "
                f"Defaults to {self.DEFAULT_MAX_ENTRIES}."
              ),
              "minimum": 1,
              "maximum": self.ABSOLUTE_MAX_ENTRIES,
            },
            "pattern": {
              "type": "string",
              "description": (
                "Optional glob pattern to filter entries "
                '(e.g., "*.py" for Python files)'
              ),
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """List directory contents with optional filtering and limits.

    Args:
      **kwargs: Must contain 'path'. May contain 'max_depth',
        'max_entries', and 'pattern'.

    Returns:
      ToolResult with formatted directory listing or error message.
    """
    path_str = kwargs.get("path", "")
    if not path_str:
      return ToolResult(
        success=False, result="", error="Missing required parameter: path"
      )

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "list_guardrail_blocked",
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
      max_depth = self._clamp(
        int(kwargs.get("max_depth", self.DEFAULT_MAX_DEPTH)),
        0,
        self.ABSOLUTE_MAX_DEPTH,
      )
      max_entries = self._clamp(
        int(kwargs.get("max_entries", self.DEFAULT_MAX_ENTRIES)),
        1,
        self.ABSOLUTE_MAX_ENTRIES,
      )
    except (ValueError, TypeError):
      return ToolResult(
        success=False, result="", error="Invalid numeric parameter"
      )

    pattern = kwargs.get("pattern", "")
    if pattern is None:
      pattern = ""

    try:
      path = Path(path_str)
      if not path.exists():
        return ToolResult(
          success=False, result="", error=f"Path not found: {path_str}"
        )

      # If path is a file, return it as a single entry
      if not path.is_dir():
        return ToolResult(
          success=True,
          result=f"{path.name}\n\n1 entry total (1 file, 0 directories)",
        )

      # Build tree listing
      lines, file_count, dir_count, truncated = self._build_tree(
        path, max_depth, max_entries, pattern
      )

      total = file_count + dir_count
      lines.append("")
      lines.append(
        f"{total} entries total ({file_count} files, {dir_count} directories)"
      )
      if truncated:
        lines.append(
          f"... ({truncated} more entries truncated, max_entries={max_entries})"
        )

      return ToolResult(success=True, result="\n".join(lines))

    except PermissionError:
      return ToolResult(
        success=False, result="", error=f"Permission denied: {path_str}"
      )
    except Exception as e:
      return ToolResult(
        success=False, result="", error=f"Error listing directory: {e}"
      )

  def _clamp(self, value: int, minimum: int, maximum: int) -> int:
    """Clamp a value to a range."""
    return max(minimum, min(value, maximum))

  def _build_tree(
    self,
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

        # Do not follow symlinks
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
