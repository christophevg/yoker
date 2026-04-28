"""Read tool implementation for Yoker.

Provides the ReadTool for reading file contents with guardrail validation,
path resolution, symlink rejection, and explicit encoding.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class ReadTool(Tool):
  """Tool for reading file contents.

  Reads the entire contents of a file as text with defense-in-depth
  validation. When a guardrail is provided, validates parameters
  before reading. Resolves paths with realpath, rejects symlinks by
  default, and reads with explicit UTF-8 encoding.

  Error messages returned to the LLM are sanitized to avoid leaking
  filesystem structure. Full paths are logged internally for debugging.
  """

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize ReadTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "read"

  @property
  def description(self) -> str:
    return "Read the contents of a file"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the read tool.

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
              "description": "Path to the file to read",
            }
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Read a file and return its contents.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Resolve the path with os.path.realpath().
      3. Reject symlinks unless explicitly allowed.
      4. Verify the file exists.
      5. Read with UTF-8 encoding and replacement for invalid bytes.
      6. Log access for audit trail.

    Args:
      **kwargs: Must contain 'path' key with file path.

    Returns:
      ToolResult with file content or sanitized error message.
    """
    path_str = kwargs.get("path", "")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "read_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Ensure path is a string
    if not isinstance(path_str, str):
      log.warning("read_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path parameter",
      )

    # Reject symlinks before resolving to prevent traversal via symlinks
    original_path = Path(path_str)
    if original_path.is_symlink():
      log.warning("read_symlink_rejected", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Reading symlinks is not permitted",
      )

    # Resolve the path to prevent traversal and normalize
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("read_invalid_path", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )

    # Verify the resolved path exists and is a file
    if not resolved.exists():
      log.info("read_file_not_found", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="File not found",
      )

    if not resolved.is_file():
      log.info("read_not_a_file", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Path is not a file",
      )

    # Read the file with explicit encoding
    try:
      content = resolved.read_text(encoding="utf-8", errors="replace")
      log.info(
        "read_success",
        path=str(resolved),
        bytes=len(content.encode("utf-8")),
      )
      return ToolResult(success=True, result=content)
    except PermissionError:
      log.warning("read_permission_denied", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Permission denied",
      )
    except OSError as e:
      log.error("read_os_error", path=str(resolved), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error="Error reading file",
      )
