"""Existence tool implementation for Yoker.

Provides the ``existence`` async function for checking if files and folders
exist. Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from structlog import get_logger

from yoker.annotations import Path as PathArg
from yoker.tools.schema import ToolResult
from yoker.tools.context import ToolContext

if TYPE_CHECKING:
  pass

log = get_logger(__name__)


async def existence(
  path: Annotated[str, PathArg("Path to check for existence")],
  ctx: ToolContext,
) -> ToolResult:
  """Check if a file or folder exists at the given path.

  Args:
    path: Path to check for existence.
    ctx: Tool execution context with configuration.

  Returns:
    ToolResult with existence check result.
  """
  if not isinstance(path, str):
    log.warning("existence_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  if not path.strip():
    log.warning("existence_empty_path")
    return ToolResult(success=False, error="Parameter 'path' cannot be empty")

  original_path = Path(path)
  if original_path.is_symlink():
    log.warning("existence_symlink_rejected", path=path)
    return ToolResult(success=False, error="Path not accessible")

  try:
    resolved = Path(os.path.realpath(path))
  except (OSError, ValueError):
    log.warning("existence_invalid_path", path=path)
    return ToolResult(success=False, error="Invalid path")

  try:
    if resolved.exists():
      if resolved.is_file():
        path_type = "file"
      elif resolved.is_dir():
        path_type = "directory"
      else:
        path_type = "other"

      log.info("existence_check_success", path=str(resolved), exists=True, type=path_type)
      return ToolResult(
        success=True,
        result={"exists": True, "type": path_type, "path": str(resolved)},
      )

    log.info("existence_check_success", path=str(resolved), exists=False, type=None)
    return ToolResult(
      success=True,
      result={"exists": False, "type": None, "path": str(resolved)},
    )
  except PermissionError:
    log.warning("existence_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Path check failed")
  except OSError as e:
    log.error("existence_os_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Path check failed")


__all__ = ["existence"]
