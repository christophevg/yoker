"""Mkdir tool implementation for Yoker.

Provides the ``mkdir`` async function for creating directories.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from structlog import get_logger

from yoker.tools.annotations import Path as PathArg
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


async def mkdir(
  path: Annotated[str, PathArg("Path to the directory to create")],
  ctx: ToolContext,
  recursive: bool = False,
) -> ToolResult:
  """Create a directory at the given path.

  Args:
    path: Path to the directory to create.
    ctx: Tool execution context with configuration.
    recursive: Whether to create parent directories.

  Returns:
    ToolResult with creation result.
  """
  if not isinstance(path, str):
    logger.warning("mkdir_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  if not path.strip():
    logger.warning("mkdir_empty_path")
    return ToolResult(success=False, error="Parameter 'path' cannot be empty")

  original_path = Path(path)
  if original_path.is_symlink():
    logger.warning("mkdir_symlink_rejected", path=path)
    return ToolResult(success=False, error="Path not accessible")

  try:
    resolved = Path(os.path.realpath(path))
  except (OSError, ValueError):
    logger.warning("mkdir_invalid_path", path=path)
    return ToolResult(success=False, error="Invalid path")

  try:
    if resolved.exists():
      if resolved.is_file():
        logger.warning("mkdir_path_is_file", path=str(resolved))
        return ToolResult(success=False, error="Path not accessible")
      elif resolved.is_dir():
        logger.info("mkdir_already_exists", path=str(resolved), recursive=recursive)
        return ToolResult(
          success=True,
          result={
            "created": False,
            "path": str(resolved),
            "message": "Directory already exists",
          },
        )
  except PermissionError:
    logger.warning("mkdir_permission_denied_check", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")

  parent = resolved.parent
  if not recursive and not parent.exists():
    logger.info("mkdir_parent_missing", path=str(resolved))
    return ToolResult(success=False, error="Parent directory does not exist")

  try:
    if recursive:
      resolved.mkdir(parents=True, exist_ok=True)
      logger.info("mkdir_created_recursive", path=str(resolved))
    else:
      resolved.mkdir(parents=False, exist_ok=False)
      logger.info("mkdir_created", path=str(resolved))

    return ToolResult(
      success=True,
      result={"created": True, "path": str(resolved)},
    )
  except PermissionError:
    logger.warning("mkdir_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except ValueError as e:
    logger.warning("mkdir_invalid_path", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Invalid path")
  except OSError as e:
    logger.error("mkdir_os_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Error creating directory")


__all__ = ["mkdir"]
