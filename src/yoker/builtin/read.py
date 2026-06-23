"""Read tool implementation for Yoker.

Provides the ``read`` async function for reading file contents.
Guardrail validation is enforced centrally by the harness based on the
schema's ``path`` annotation.
"""

import os
from pathlib import Path
from typing import Annotated

from structlog import get_logger

from yoker.resources import find_package_path, parse_plugin_url
from yoker.tools.annotations import Path as PathArg
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)


async def read(
  path: Annotated[str, PathArg("Path to the file to read (or plugin:// URL)")],
  ctx: ToolContext,
) -> ToolResult:
  """Read the contents of a file.

  Args:
    path: Path to the file to read.
    ctx: Tool execution context with configuration.

  Returns:
    ToolResult with file contents.
  """
  if not isinstance(path, str):
    logger.warning("read_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  if path.startswith("plugin://"):
    return await _read_plugin_resource(path)

  return await _read_file(path)


async def _read_plugin_resource(url: str) -> ToolResult:
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
  return ToolResult(success=True, result=content)


async def _read_file(path_str: str) -> ToolResult:
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
    logger.info("read_success", path=str(resolved), bytes=len(content.encode("utf-8")))
    return ToolResult(success=True, result=content)
  except PermissionError:
    logger.warning("read_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except OSError as e:
    logger.error("read_os_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Error reading file")


__all__ = ["read"]
