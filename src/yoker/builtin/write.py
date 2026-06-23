"""Write tool implementation for Yoker.

Provides the ``write`` async function for writing file contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.tools.annotations import Path as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


def _is_binary(content: str) -> bool:
  """Check if content appears to be binary."""
  check_size = min(len(content), 8192)
  return "\x00" in content[:check_size]


def _truncate_content(
  content: str,
  max_lines: int,
  max_bytes: int,
) -> tuple[str, bool, int, int]:
  """Truncate content based on max lines and max bytes."""
  original_bytes = len(content.encode("utf-8"))
  lines = content.splitlines(keepends=True)
  original_lines_count = len(lines)

  if len(lines) > max_lines:
    lines = lines[:max_lines]
    was_truncated = True
  else:
    was_truncated = False

  truncated_content = "".join(lines)
  truncated_bytes = len(truncated_content.encode("utf-8"))

  if truncated_bytes > max_bytes:
    truncated_content = truncated_content[:max_bytes]
    was_truncated = True

  return truncated_content, was_truncated, original_lines_count, original_bytes


async def write(
  path: Annotated[str, PathArg("Path to the file to write")],
  content: Annotated[str, Text("Content to write to the file")],
  ctx: ToolContext,
  create_parents: bool = False,
) -> ToolResult:
  """Write content to a file."""
  # Config values come from ctx.config (WriteToolConfig with defaults)
  write_config = ctx.config
  allow_overwrite = write_config.allow_overwrite

  if not isinstance(path, str) or not path.strip():
    logger.warning("write_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  if not isinstance(content, str):
    logger.warning("write_invalid_content_type", content_type=type(content).__name__)
    return ToolResult(success=False, error="Invalid content parameter")

  original_path = Path(path)
  if original_path.is_symlink():
    logger.warning("write_symlink_rejected", path=path)
    return ToolResult(success=False, error="Writing to symlinks is not permitted")

  try:
    resolved = Path(os.path.realpath(path))
  except (OSError, ValueError):
    logger.warning("write_invalid_path", path=path)
    return ToolResult(success=False, error="Invalid path")

  is_overwrite = resolved.exists()
  if is_overwrite:
    if not allow_overwrite:
      logger.info("write_overwrite_blocked", path=str(resolved))
      return ToolResult(success=False, error="File already exists and overwrite is not permitted")

  parent = resolved.parent
  if not parent.exists():
    if create_parents:
      try:
        parent.mkdir(parents=True, exist_ok=True)
        logger.info("write_created_parents", path=str(parent))
      except OSError as e:
        logger.error("write_create_parents_failed", path=str(parent), error=str(e))
        return ToolResult(success=False, error="Failed to create parent directories")
    else:
      logger.info("write_parent_missing", path=str(resolved))
      return ToolResult(success=False, error="Parent directory does not exist")

  try:
    resolved.write_text(content, encoding="utf-8")
    logger.info("write_success", path=str(resolved), bytes=len(content.encode("utf-8")))

    content_metadata = _build_content_metadata(
      content=content,
      resolved_path=resolved,
      is_overwrite=is_overwrite,
      ctx=ctx,
    )

    return ToolResult(
      success=True,
      result="File written successfully",
      content_metadata=content_metadata,
    )
  except PermissionError:
    logger.warning("write_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except OSError as e:
    logger.error("write_os_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Error writing file")


def _build_content_metadata(
  content: str,
  resolved_path: Path,
  is_overwrite: bool,
  ctx: ToolContext | None,
) -> dict[str, Any] | None:
  """Build content_metadata for ToolResult."""
  # Get content display config from context or use defaults
  if ctx is not None:
    content_display = ctx.shared.content_display
  else:
    # Fallback defaults
    from yoker.config import ContentDisplayConfig

    content_display = ContentDisplayConfig()

  if content_display.verbosity == "silent":
    return None

  is_binary = _is_binary(content)
  if is_binary:
    byte_size = len(content.encode("utf-8"))
    return {
      "operation": "write",
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "lines": 0,
        "bytes": byte_size,
        "is_new_file": not is_overwrite,
        "is_overwrite": is_overwrite,
        "is_binary": True,
      },
    }

  lines = content.splitlines()
  line_count = len(lines)
  byte_size = len(content.encode("utf-8"))
  is_empty = line_count == 0

  if content_display.verbosity == "summary":
    return {
      "operation": "write",
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "lines": line_count,
        "bytes": byte_size,
        "is_new_file": not is_overwrite,
        "is_overwrite": is_overwrite,
        "is_empty": is_empty,
      },
    }

  truncated_content, was_truncated, _, _ = _truncate_content(
    content,
    content_display.max_content_lines,
    content_display.max_content_bytes,
  )

  metadata: dict[str, Any] = {
    "lines": line_count,
    "bytes": byte_size,
    "is_new_file": not is_overwrite,
    "is_overwrite": is_overwrite,
    "is_empty": is_empty,
  }

  if was_truncated:
    metadata["truncated"] = True
    metadata["original_line_count"] = line_count

  return {
    "operation": "write",
    "path": str(resolved_path),
    "content_type": "text/plain",
    "content": truncated_content,
    "metadata": metadata,
  }


__all__ = ["write"]
