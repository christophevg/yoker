"""File tool implementation for Yoker.

Provides the ``file`` async function for filesystem operations: copy,
move, and delete. Guardrails are enforced centrally by the harness based
on the schema's path annotations — both ``source`` and ``destination``
are validated as filesystem paths.

Design: a single tool with an ``operation`` parameter (like ``git``),
not separate tools. This keeps the toolset compact and the operation
enum acts as a security boundary — only the listed operations are
allowed.
"""

import os
import shutil
from pathlib import Path
from typing import Annotated

from structlog import get_logger

from yoker.config import FileToolConfig
from yoker.tools.annotations import Path as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

# Directories that must never be deleted recursively.
_NEVER_DELETE_DIRS: frozenset[str] = frozenset({".git", ".svn", ".hg"})

# Operations supported by the file tool.
_OPERATIONS: frozenset[str] = frozenset({"copy", "move", "delete"})


async def file(
  operation: Annotated[
    str,
    Text("File operation to execute. One of: copy, move, delete."),
  ],
  source: Annotated[str, PathArg("Path to the source file or directory")],
  ctx: ToolContext,
  destination: Annotated[
    str | None,
    PathArg("Destination path (required for copy and move, not used for delete)"),
  ] = None,
  recursive: bool = False,
) -> ToolResult:
  """Execute a filesystem operation on a file or directory.

  Operations:
    - copy: Copy a file or directory tree from source to destination.
    - move: Move/rename a file or directory from source to destination.
    - delete: Delete a file or directory (requires recursive=True for
      directories).

  For copy and move:
    - ``destination`` is required.
    - If ``source`` is a directory, ``recursive`` must be True.
    - If ``destination`` already exists, the operation fails (no silent
      overwrite). Use delete first if you intend to replace.

  For delete:
    - ``destination`` is not used.
    - Deleting a directory requires ``recursive=True``.
    - The ``.git`` directory is never deleted, even with recursive=True.
  """
  file_config = ctx.config
  if not isinstance(file_config, FileToolConfig):
    logger.warning("file_invalid_config_type", config_type=type(file_config).__name__)
    return ToolResult(success=False, error="Invalid configuration for file tool")

  if not isinstance(operation, str) or not operation.strip():
    return ToolResult(success=False, error="Missing required parameter: operation")

  if operation not in _OPERATIONS:
    return ToolResult(
      success=False,
      error=f"Unknown operation: {operation}. Allowed: {', '.join(sorted(_OPERATIONS))}",
    )

  if not isinstance(source, str) or not source.strip():
    return ToolResult(success=False, error="Parameter 'source' cannot be empty")

  # Resolve source
  original_source = Path(source)
  if original_source.is_symlink():
    logger.warning("file_source_symlink_rejected", source=source)
    return ToolResult(success=False, error="Source path is a symlink, not permitted")

  try:
    resolved_source = Path(os.path.realpath(source))
  except (OSError, ValueError):
    return ToolResult(success=False, error="Invalid source path")

  if not resolved_source.exists():
    return ToolResult(success=False, error=f"Source does not exist: {source}")

  # Resolve destination for copy/move
  resolved_destination: Path | None = None
  if operation in ("copy", "move"):
    if not isinstance(destination, str) or not destination.strip():
      return ToolResult(
        success=False, error=f"Parameter 'destination' is required for operation '{operation}'"
      )

    original_dest = Path(destination)
    if original_dest.is_symlink():
      logger.warning("file_dest_symlink_rejected", destination=destination)
      return ToolResult(success=False, error="Destination path is a symlink, not permitted")

    try:
      resolved_destination = Path(os.path.realpath(destination))
    except (OSError, ValueError):
      return ToolResult(success=False, error="Invalid destination path")

    if resolved_destination == resolved_source:
      return ToolResult(success=False, error="Source and destination are the same path")

    if resolved_destination.exists():
      return ToolResult(
        success=False,
        error=f"Destination already exists: {destination}. Delete it first if you intend to replace.",
      )

  # Dispatch to operation handler
  if operation == "copy":
    return _do_copy(resolved_source, resolved_destination, recursive)
  elif operation == "move":
    return _do_move(resolved_source, resolved_destination, recursive)
  elif operation == "delete":
    return _do_delete(resolved_source, recursive)
  else:
    # Unreachable — operation already validated above
    return ToolResult(success=False, error=f"Unknown operation: {operation}")


def _do_copy(source: Path, destination: Path | None, recursive: bool) -> ToolResult:
  """Copy a file or directory tree."""
  assert destination is not None  # validated by caller

  if source.is_dir():
    if not recursive:
      return ToolResult(
        success=False,
        error="Source is a directory. Set recursive=True to copy directories.",
      )
    try:
      shutil.copytree(source, destination)
      logger.info("file_copy_dir_success", source=str(source), destination=str(destination))
      return ToolResult(
        success=True,
        result={
          "operation": "copy",
          "source": str(source),
          "destination": str(destination),
          "type": "directory",
        },
      )
    except PermissionError:
      return ToolResult(success=False, error="Permission denied")
    except OSError as e:
      logger.error("file_copy_dir_error", source=str(source), error=str(e))
      return ToolResult(success=False, error=f"Error copying directory: {e}")
  else:
    try:
      # Ensure parent directory of destination exists
      destination.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(source, destination)
      logger.info("file_copy_file_success", source=str(source), destination=str(destination))
      return ToolResult(
        success=True,
        result={
          "operation": "copy",
          "source": str(source),
          "destination": str(destination),
          "type": "file",
        },
      )
    except PermissionError:
      return ToolResult(success=False, error="Permission denied")
    except OSError as e:
      logger.error("file_copy_file_error", source=str(source), error=str(e))
      return ToolResult(success=False, error=f"Error copying file: {e}")


def _do_move(source: Path, destination: Path | None, recursive: bool) -> ToolResult:
  """Move/rename a file or directory."""
  assert destination is not None  # validated by caller

  # shutil.move handles both files and directories, including cross-device.
  # The recursive flag is not needed for move (shutil.move handles directories
  # natively), but we accept it for API consistency and ignore it.
  try:
    # Ensure parent directory of destination exists
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    logger.info("file_move_success", source=str(source), destination=str(destination))
    source_type = "directory" if destination.is_dir() else "file"
    return ToolResult(
      success=True,
      result={
        "operation": "move",
        "source": str(source),
        "destination": str(destination),
        "type": source_type,
      },
    )
  except PermissionError:
    return ToolResult(success=False, error="Permission denied")
  except OSError as e:
    logger.error("file_move_error", source=str(source), error=str(e))
    return ToolResult(success=False, error=f"Error moving file: {e}")


def _do_delete(source: Path, recursive: bool) -> ToolResult:
  """Delete a file or directory."""
  if source.is_dir():
    # Safety: never delete .git or other VCS directories
    if source.name in _NEVER_DELETE_DIRS:
      return ToolResult(
        success=False,
        error=f"Refusing to delete VCS directory: {source.name}. This is a safety guardrail.",
      )

    if not recursive:
      return ToolResult(
        success=False,
        error="Source is a directory. Set recursive=True to delete directories.",
      )

    try:
      shutil.rmtree(source)
      logger.info("file_delete_dir_success", path=str(source))
      return ToolResult(
        success=True,
        result={"operation": "delete", "path": str(source), "type": "directory"},
      )
    except PermissionError:
      return ToolResult(success=False, error="Permission denied")
    except OSError as e:
      logger.error("file_delete_dir_error", path=str(source), error=str(e))
      return ToolResult(success=False, error=f"Error deleting directory: {e}")
  else:
    try:
      source.unlink()
      logger.info("file_delete_file_success", path=str(source))
      return ToolResult(
        success=True,
        result={"operation": "delete", "path": str(source), "type": "file"},
      )
    except PermissionError:
      return ToolResult(success=False, error="Permission denied")
    except OSError as e:
      logger.error("file_delete_file_error", path=str(source), error=str(e))
      return ToolResult(success=False, error=f"Error deleting file: {e}")


__all__ = ["file"]
