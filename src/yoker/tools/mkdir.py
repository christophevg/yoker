"""Mkdir tool implementation for Yoker.

Provides the MkdirTool for creating directories with guardrail validation,
recursive parent creation, and graceful handling of existing directories.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class MkdirTool(Tool):
  """Tool for creating directories.

  Creates a directory at the given path with optional recursive parent
  creation. When a guardrail is provided, validates parameters before
  creating. Resolves paths with realpath and rejects symlinks by default.

  Returns a structured result indicating success, creation status, and
  the resolved path for debugging.
  """

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize MkdirTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "mkdir"

  @property
  def description(self) -> str:
    return "Create a directory at the given path"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the mkdir tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
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
              "description": "Path to the directory to create",
            },
            "recursive": {
              "type": "boolean",
              "description": "If true, create parent directories as needed (like mkdir -p). Defaults to false.",
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Create a directory.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate path parameter.
      3. Reject symlinks before resolving.
      4. Resolve the path with os.path.realpath().
      5. Check if path already exists (file or directory).
      6. Create directory, optionally with parents.
      7. Return structured result with creation status.

    Args:
      **kwargs: Must contain 'path' key.
        May contain 'recursive' (default False).

    Returns:
      ToolResult with creation result or error message.
    """
    path_str = kwargs.get("path", "")
    recursive = bool(kwargs.get("recursive", False))

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "mkdir_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Validate path parameter type
    if not isinstance(path_str, str):
      log.warning("mkdir_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path parameter",
      )

    # Validate path is not empty
    if not path_str.strip():
      log.warning("mkdir_empty_path")
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'path' cannot be empty",
      )

    # Reject symlinks before resolving to prevent traversal via symlinks
    original_path = Path(path_str)
    if original_path.is_symlink():
      log.warning("mkdir_symlink_rejected", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Path not accessible",
      )

    # Resolve the path to normalize
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("mkdir_invalid_path", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )

    # Check what exists at the path
    try:
      if resolved.exists():
        if resolved.is_file():
          log.warning("mkdir_path_is_file", path=str(resolved))
          return ToolResult(
            success=False,
            result="",
            error="Path not accessible",
          )
        elif resolved.is_dir():
          # Directory already exists - idempotent success
          log.info(
            "mkdir_already_exists",
            path=str(resolved),
            recursive=recursive,
          )
          return ToolResult(
            success=True,
            result={
              "created": False,
              "path": str(resolved),
              "message": "Directory already exists",
            },
          )
    except PermissionError:
      log.warning("mkdir_permission_denied_check", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Permission denied",
      )

    # Check parent exists for non-recursive mode
    parent = resolved.parent
    if not recursive and not parent.exists():
      log.info("mkdir_parent_missing", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Parent directory does not exist",
      )

    # Create directory
    try:
      if recursive:
        resolved.mkdir(parents=True, exist_ok=True)
        log.info("mkdir_created_recursive", path=str(resolved))
      else:
        resolved.mkdir(parents=False, exist_ok=False)
        log.info("mkdir_created", path=str(resolved))

      return ToolResult(
        success=True,
        result={
          "created": True,
          "path": str(resolved),
        },
      )

    except PermissionError:
      log.warning("mkdir_permission_denied", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Permission denied",
      )
    except ValueError as e:
      # Windows raises ValueError for paths with null bytes
      log.warning("mkdir_invalid_path", path=str(resolved), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )
    except OSError as e:
      log.error("mkdir_os_error", path=str(resolved), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error="Error creating directory",
      )
