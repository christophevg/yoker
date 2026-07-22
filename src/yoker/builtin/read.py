"""Read tool implementation for Yoker.

Provides the ``read`` async function for reading file contents.
Guardrail validation is enforced centrally by the harness based on the
schema's ``path`` annotation.
"""

import os
from pathlib import Path
from typing import Annotated, Any

from structlog import get_logger

from yoker.resources import find_package_path, parse_plugin_url
from yoker.tools.annotations import Path as PathArg
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

# cat -n renders line numbers in a 6-wide right-aligned field.
CAT_N_WIDTH = 6


async def read(
  path: Annotated[str, PathArg("Path to the file to read (or plugin:// URL)")],
  ctx: ToolContext,
  offset: int | None = None,
  limit: int | None = None,
) -> ToolResult:
  """Read the contents of a file, optionally sliced by line range.

  When neither ``offset`` nor ``limit`` is provided, the full file content is
  returned unchanged (byte-identical to the historical behavior, no prefix,
  no metadata). When either is provided, the result is formatted ``cat -n``
  style with a right-aligned line-number prefix, and ``content_metadata``
  describes the slice with the flat shape consumed by ``ToolContentEvent``.
  """
  if not isinstance(path, str):
    logger.warning("read_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  # Validate offset/limit before any I/O — cheap, deterministic, no file access.
  validation_error = _validate_offset_limit(offset, limit)
  if validation_error is not None:
    return ToolResult(success=False, error=validation_error)

  if path.startswith("plugin://"):
    return await _read_plugin_resource(path, offset, limit)

  return await _read_file(path, offset, limit)


def _validate_offset_limit(offset: int | None, limit: int | None) -> str | None:
  """Return an error string if offset/limit are invalid, else None."""
  if offset is not None:
    if not isinstance(offset, int):
      return "offset must be an integer"
    if offset < 1:
      return "offset must be >= 1"
  if limit is not None:
    if not isinstance(limit, int):
      return "limit must be an integer"
    if limit < 1:
      return "limit must be >= 1"
  return None


def _apply_offset_limit(
  text: str, offset: int | None, limit: int | None, resolved_path: str
) -> dict[str, Any]:
  """Slice text by 1-indexed line range and render with a cat -n prefix.

  Returns the flat ``content_metadata`` dict consumed by ``ToolContentEvent``:
  ``operation``, ``path``, ``content_type``, ``content``, and a nested
  ``metadata`` with the read-specific fields.
  """
  lines = text.splitlines(keepends=True)
  total = len(lines)
  start_line = offset if offset is not None else 1
  start = start_line - 1
  end = start + limit if limit is not None else total
  sliced = lines[start:end]
  actual_count = len(sliced)
  numbered = "".join(f"{start + i + 1:>{CAT_N_WIDTH}}\t{line}" for i, line in enumerate(sliced))
  return {
    "operation": "read",
    "path": resolved_path,
    "content_type": "text/plain",
    "content": numbered,
    "metadata": {
      "offset": start_line,
      "limit": limit,
      "total_lines": total,
      "returned_lines": actual_count,
    },
  }


def _finalize_read(
  content: str, offset: int | None, limit: int | None, resolved_path: str
) -> ToolResult:
  """Build the final ToolResult, applying offset/limit if requested.

  When neither ``offset`` nor ``limit`` is set, returns the raw content with
  no metadata (byte-identical to the historical behavior). Otherwise renders
  the slice ``cat -n`` style and attaches the flat ``content_metadata``.
  """
  if offset is None and limit is None:
    return ToolResult(success=True, result=content)
  metadata = _apply_offset_limit(content, offset, limit, resolved_path)
  return ToolResult(success=True, result=metadata["content"], content_metadata=metadata)


async def _read_plugin_resource(url: str, offset: int | None, limit: int | None) -> ToolResult:
  """Read a file from a Python package using a plugin:// URL.

  Agent URLs (``plugin://pkg/agents/<name>``) are rejected — this tool reads
  files, not agent definitions. The subpath is resolved via
  :func:`yoker.resources.find_package_path`, which works for installed
  packages and returns None when the package or resource is absent.
  """
  try:
    parsed = parse_plugin_url(url)
  except ValueError as e:
    logger.warning("plugin_resource_invalid_url", url=url, error=str(e))
    return ToolResult(success=False, error=f"Invalid plugin URL: {e}")

  # Reject agent URLs and empty subpaths.
  sub_parts = parsed.subpath.split("/")
  is_agent = len(sub_parts) >= 2 and sub_parts[0] == "agents" and sub_parts[1]
  if is_agent or not parsed.subpath:
    return ToolResult(
      success=False, error="Invalid plugin URL format. Use: plugin://package/path/to/file"
    )

  logger.info("reading_plugin_resource", package=parsed.package, path=parsed.subpath)
  resource = find_package_path(parsed.package, parsed.subpath)
  if resource is None:
    logger.warning("plugin_resource_not_found", package=parsed.package, path=parsed.subpath)
    return ToolResult(success=False, error=f"Resource not found in package: {parsed.subpath}")

  try:
    content = resource.read_text(encoding="utf-8")
  except Exception as e:
    logger.error("plugin_resource_error", package=parsed.package, path=parsed.subpath, error=str(e))
    return ToolResult(success=False, error=f"Error reading plugin resource: {e}")

  logger.info(
    "plugin_resource_read_success",
    package=parsed.package,
    path=parsed.subpath,
    bytes=len(content.encode("utf-8")),
  )
  return _finalize_read(content, offset, limit, str(resource))


async def _read_file(path_str: str, offset: int | None, limit: int | None) -> ToolResult:
  """Read a regular file from the filesystem."""
  original_path = Path(path_str)
  if original_path.is_symlink():
    logger.warning("read_symlink_rejected", path=path_str)
    return ToolResult(success=False, error="Reading symlinks is not permitted")

  try:
    resolved = Path(os.path.realpath(path_str))
  except (OSError, ValueError):
    logger.warning("read_invalid_path", path=path_str)
    return ToolResult(success=False, error="Invalid path")

  if not resolved.exists():
    logger.info("read_file_not_found", path=str(resolved))
    return ToolResult(success=False, error="File not found")

  if not resolved.is_file():
    logger.info("read_not_a_file", path=str(resolved))
    return ToolResult(success=False, error="Path is not a file")

  try:
    content = resolved.read_text(encoding="utf-8", errors="replace")
  except PermissionError:
    logger.warning("read_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except OSError as e:
    logger.error("read_os_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Error reading file")

  logger.info("read_success", path=str(resolved), bytes=len(content.encode("utf-8")))
  return _finalize_read(content, offset, limit, str(resolved))


__all__ = ["read"]
