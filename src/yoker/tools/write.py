"""Write tool implementation for Yoker.

Provides the WriteTool for writing file contents with guardrail validation,
overwrite protection, and explicit parent directory handling.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.config.schema import Config
from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class WriteTool(Tool):
  """Tool for writing file contents.

  Writes content to a file with defense-in-depth validation.
  When a guardrail is provided, validates parameters before writing.
  Resolves paths with realpath, rejects symlinks, and supports
  overwrite protection and parent directory creation.

  Error messages returned to the LLM are sanitized to avoid leaking
  filesystem structure. Full paths are logged internally for debugging.
  """

  def __init__(
    self,
    guardrail: "Guardrail | None" = None,
    config: Config | None = None,
  ) -> None:
    """Initialize WriteTool with optional guardrail and config.

    Args:
      guardrail: Optional guardrail for parameter validation.
      config: Optional config for overwrite protection and size limits.
        If not provided, defaults to Config() (allow_overwrite=False).
    """
    super().__init__(guardrail=guardrail)
    self._config = config or Config()

  @property
  def name(self) -> str:
    return "write"

  @property
  def description(self) -> str:
    return "Write content to a file"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the write tool.

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
              "description": "Path to the file to write",
            },
            "content": {
              "type": "string",
              "description": "Content to write to the file",
            },
            "create_parents": {
              "type": "boolean",
              "description": ("If true, create missing parent directories. Defaults to false."),
            },
          },
          "required": ["path", "content"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Write content to a file.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate path and content parameters.
      3. Resolve the path with os.path.realpath().
      4. Reject symlinks unless explicitly allowed.
      5. Check overwrite protection (config-based).
      6. Create parent directories if requested.
      7. Write with UTF-8 encoding.
      8. Log write for audit trail.

    Args:
      **kwargs: Must contain 'path' and 'content' keys.
        May contain 'create_parents' (default False).

    Returns:
      ToolResult with success status and output or error message.
    """
    path_str = kwargs.get("path", "")
    content = kwargs.get("content", "")
    create_parents = bool(kwargs.get("create_parents", False))

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "write_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Ensure path is a non-empty string
    if not isinstance(path_str, str) or not path_str.strip():
      log.warning("write_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(success=False, result="", error="Invalid path parameter")

    # Ensure content is a string (empty content is valid)
    if not isinstance(content, str):
      log.warning(
        "write_invalid_content_type",
        content_type=type(content).__name__,
      )
      return ToolResult(success=False, result="", error="Invalid content parameter")

    # Reject symlinks before resolving to prevent traversal via symlinks
    original_path = Path(path_str)
    if original_path.is_symlink():
      log.warning("write_symlink_rejected", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Writing to symlinks is not permitted",
      )

    # Resolve the path to prevent traversal and normalize
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("write_invalid_path", path=path_str)
      return ToolResult(success=False, result="", error="Invalid path")

    # Check overwrite protection
    if resolved.exists():
      allow_overwrite = self._config.tools.write.allow_overwrite
      if not allow_overwrite:
        log.info(
          "write_overwrite_blocked",
          path=str(resolved),
        )
        return ToolResult(
          success=False,
          result="",
          error="File already exists and overwrite is not permitted",
        )

    # Check parent directory
    parent = resolved.parent
    if not parent.exists():
      if create_parents:
        try:
          parent.mkdir(parents=True, exist_ok=True)
          log.info(
            "write_created_parents",
            path=str(parent),
          )
        except OSError as e:
          log.error(
            "write_create_parents_failed",
            path=str(parent),
            error=str(e),
          )
          return ToolResult(
            success=False,
            result="",
            error="Failed to create parent directories",
          )
      else:
        log.info("write_parent_missing", path=str(resolved))
        return ToolResult(
          success=False,
          result="",
          error="Parent directory does not exist",
        )

    # Write the file with explicit encoding
    try:
      resolved.write_text(content, encoding="utf-8")
      log.info(
        "write_success",
        path=str(resolved),
        bytes=len(content.encode("utf-8")),
      )
      return ToolResult(success=True, result="File written successfully")
    except PermissionError:
      log.warning("write_permission_denied", path=str(resolved))
      return ToolResult(success=False, result="", error="Permission denied")
    except OSError as e:
      log.error("write_os_error", path=str(resolved), error=str(e))
      return ToolResult(success=False, result="", error="Error writing file")
