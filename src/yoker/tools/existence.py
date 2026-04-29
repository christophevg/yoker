"""Existence tool implementation for Yoker.

Provides the ExistenceTool for checking if files and folders exist with
guardrail validation, path resolution, and symlink rejection.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class ExistenceTool(Tool):
  """Tool for checking file or folder existence.

  Checks whether a file or directory exists at the given path.
  When a guardrail is provided, validates parameters before checking.
  Resolves paths with realpath and rejects symlinks by default.

  Returns a structured result indicating existence, type (file/directory),
  and the resolved path for debugging.
  """

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize ExistenceTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "existence"

  @property
  def description(self) -> str:
    return "Check if a file or folder exists at the given path"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the existence tool.

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
              "description": "Path to check for existence",
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Check if a file or folder exists.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Validate path parameter is a non-empty string.
      3. Reject symlinks before resolving.
      4. Resolve the path with os.path.realpath().
      5. Check existence and type (file or directory).
      6. Return structured result with boolean existence flag.

    Args:
      **kwargs: Must contain 'path' key with path to check.

    Returns:
      ToolResult with existence check result or error message.
    """
    path_str = kwargs.get("path", "")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "existence_guardrail_blocked",
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
      log.warning("existence_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path parameter",
      )

    # Validate path is not empty
    if not path_str.strip():
      log.warning("existence_empty_path")
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'path' cannot be empty",
      )

    # Reject symlinks before resolving to prevent traversal via symlinks
    original_path = Path(path_str)
    if original_path.is_symlink():
      log.warning("existence_symlink_rejected", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Path not accessible",
      )

    # Resolve the path to normalize
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("existence_invalid_path", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )

    # Check existence and type
    try:
      if resolved.exists():
        if resolved.is_file():
          path_type = "file"
        elif resolved.is_dir():
          path_type = "directory"
        else:
          # Could be a socket, device, etc.
          path_type = "other"

        log.info(
          "existence_check_success",
          path=str(resolved),
          exists=True,
          type=path_type,
        )

        return ToolResult(
          success=True,
          result={
            "exists": True,
            "type": path_type,
            "path": str(resolved),
          },
        )
      else:
        log.info(
          "existence_check_success",
          path=str(resolved),
          exists=False,
          type=None,
        )

        return ToolResult(
          success=True,
          result={
            "exists": False,
            "type": None,
            "path": str(resolved),
          },
        )

    except PermissionError:
      log.warning("existence_permission_denied", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Path check failed",
      )
    except OSError as e:
      log.error("existence_os_error", path=str(resolved), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error="Path check failed",
      )
