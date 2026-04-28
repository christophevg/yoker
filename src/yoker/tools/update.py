"""Update tool implementation for Yoker.

Provides the UpdateTool for editing existing file contents with guardrail
validation, exact match enforcement, diff size limits, and atomic writes.
Supports replace, insert_before, insert_after, and delete operations.
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


class UpdateTool(Tool):
  """Tool for updating existing file contents.

  Edits files via replace, insert_before, insert_after, or delete operations.
  When a guardrail is provided, validates parameters before updating.
  Resolves paths with realpath, rejects symlinks, and enforces exact
  match validation and diff size limits via config.

  Error messages returned to the LLM are sanitized to avoid leaking
  filesystem structure. Full paths are logged internally for debugging.
  """

  def __init__(
    self,
    guardrail: "Guardrail | None" = None,
    config: Config | None = None,
  ) -> None:
    """Initialize UpdateTool with optional guardrail and config.

    Args:
      guardrail: Optional guardrail for parameter validation.
      config: Optional config for exact match and diff size settings.
        If not provided, defaults to Config() (require_exact_match=True).
    """
    super().__init__(guardrail=guardrail)
    self._config = config or Config()

  @property
  def name(self) -> str:
    return "update"

  @property
  def description(self) -> str:
    return "Update an existing file by replacing, inserting, or deleting content"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the update tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": (
          "Update an existing file by replacing, inserting, or deleting content. "
          "The file must exist. For replace and delete, old_string must match "
          "exactly. For insert operations, line_number is required (1-indexed)."
        ),
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Path to the file to update",
            },
            "operation": {
              "type": "string",
              "enum": ["replace", "insert_before", "insert_after", "delete"],
              "description": "Type of edit operation",
            },
            "old_string": {
              "type": "string",
              "description": (
                "Text to find (required for replace and delete). "
                "Must match exactly when require_exact_match is true."
              ),
            },
            "new_string": {
              "type": "string",
              "description": ("Replacement or insertion text (required for replace and insert)."),
            },
            "line_number": {
              "type": "integer",
              "description": (
                "Line number for insert/delete operations (1-indexed). "
                "Required for insert_before, insert_after, and line-based delete."
              ),
            },
          },
          "required": ["path", "operation"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Update an existing file.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate path, operation, and content parameters.
      3. Resolve the path with os.path.realpath().
      4. Reject symlinks unless explicitly allowed.
      5. Verify file exists and is a file (not a directory).
      6. Read file fresh to prevent TOCTOU race conditions.
      7. Validate diff size against config limit.
      8. Perform the requested operation with exact match validation.
      9. Write atomically via temp file + os.replace().
     10. Log update for audit trail.

    Args:
      **kwargs: Must contain 'path' and 'operation' keys.
        May contain 'old_string', 'new_string', 'line_number'.

    Returns:
      ToolResult with success status and output or error message.
    """
    path_str = kwargs.get("path", "")
    operation = kwargs.get("operation", "")
    old_string = kwargs.get("old_string", "")
    new_string = kwargs.get("new_string", "")
    line_number = kwargs.get("line_number")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "update_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Validate path parameter
    if not isinstance(path_str, str) or not path_str.strip():
      log.warning("update_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(success=False, result="", error="Invalid path parameter")

    # Validate operation
    valid_operations = {"replace", "insert_before", "insert_after", "delete"}
    if operation not in valid_operations:
      log.warning("update_invalid_operation", operation=operation)
      return ToolResult(success=False, result="", error="Invalid operation")

    # Validate content parameters
    if not isinstance(old_string, str):
      log.warning(
        "update_invalid_old_string_type",
        old_string_type=type(old_string).__name__,
      )
      return ToolResult(success=False, result="", error="Invalid old_string parameter")
    if not isinstance(new_string, str):
      log.warning(
        "update_invalid_new_string_type",
        new_string_type=type(new_string).__name__,
      )
      return ToolResult(success=False, result="", error="Invalid new_string parameter")

    # Reject symlinks before resolving to prevent traversal via symlinks
    try:
      original_path = Path(path_str)
      if original_path.is_symlink():
        log.warning("update_symlink_rejected", path=path_str)
        return ToolResult(
          success=False,
          result="",
          error="Updating symlinks is not permitted",
        )
    except (OSError, PermissionError):
      log.warning("update_path_access_error", path=path_str)
      return ToolResult(success=False, result="", error="Invalid path")

    # Resolve the path to prevent traversal and normalize
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("update_invalid_path", path=path_str)
      return ToolResult(success=False, result="", error="Invalid path")

    # File must exist
    if not resolved.exists():
      log.info("update_file_not_found", path=str(resolved))
      return ToolResult(success=False, result="", error="File not found")
    if not resolved.is_file():
      log.info("update_not_a_file", path=str(resolved))
      return ToolResult(success=False, result="", error="Path is not a file")

    # Read file fresh to prevent TOCTOU race conditions
    try:
      content = resolved.read_text(encoding="utf-8")
    except PermissionError:
      log.warning("update_permission_denied", path=str(resolved))
      return ToolResult(success=False, result="", error="Permission denied")
    except OSError:
      log.error("update_read_error", path=str(resolved))
      return ToolResult(success=False, result="", error="Error reading file")

    # Validate diff size against config limit
    update_config = self._config.tools.update
    max_diff_size_kb = update_config.max_diff_size_kb
    if max_diff_size_kb > 0:
      diff_size = len(new_string.encode("utf-8"))
      if diff_size > max_diff_size_kb * 1024:
        log.info(
          "update_diff_size_exceeded",
          diff_size=diff_size,
          max_diff_size_kb=max_diff_size_kb,
        )
        return ToolResult(
          success=False,
          result="",
          error="Diff size exceeds limit",
        )

    # Perform operation
    try:
      if operation == "replace":
        result_content = self._do_replace(content, old_string, new_string)
      elif operation in ("insert_before", "insert_after"):
        result_content = self._do_insert(content, operation, line_number, new_string)
      elif operation == "delete":
        result_content = self._do_delete(content, old_string, line_number)
      else:
        # Should not reach here due to earlier validation
        return ToolResult(success=False, result="", error="Invalid operation")
    except ValueError as e:
      log.info("update_validation_error", error=str(e))
      return ToolResult(success=False, result="", error=str(e))

    # Atomic write: temp file then replace
    try:
      temp_path = resolved.with_suffix(resolved.suffix + ".tmp")
      temp_path.write_text(result_content, encoding="utf-8")
      os.replace(str(temp_path), str(resolved))
      log.info(
        "update_success",
        path=str(resolved),
        operation=operation,
      )
      return ToolResult(success=True, result="File updated successfully")
    except PermissionError:
      log.warning("update_permission_denied_write", path=str(resolved))
      return ToolResult(success=False, result="", error="Permission denied")
    except OSError as e:
      log.error("update_write_error", path=str(resolved), error=str(e))
      return ToolResult(success=False, result="", error="Error updating file")

  def _do_replace(self, content: str, old_string: str, new_string: str) -> str:
    """Replace old_string with new_string in content.

    When require_exact_match is True (default), old_string must appear
    exactly once. Otherwise, replaces the first occurrence.

    Args:
      content: Original file content.
      old_string: Text to search for.
      new_string: Replacement text.

    Returns:
      Updated content string.

    Raises:
      ValueError: If old_string not found or appears multiple times
        when require_exact_match is True.
    """
    require_exact = self._config.tools.update.require_exact_match
    occurrences = content.count(old_string)

    if occurrences == 0:
      raise ValueError("Search text not found")

    if require_exact and occurrences > 1:
      raise ValueError("Search text appears multiple times; ambiguous match")

    return content.replace(old_string, new_string, 1)

  def _do_insert(
    self,
    content: str,
    operation: str,
    line_number: Any,
    new_string: str,
  ) -> str:
    """Insert new_string before or after a specific line.

    Args:
      content: Original file content.
      operation: "insert_before" or "insert_after".
      line_number: 1-indexed line number (required).
      new_string: Text to insert.

    Returns:
      Updated content string.

    Raises:
      ValueError: If line_number is missing, invalid, or out of range.
    """
    if line_number is None:
      raise ValueError("line_number is required for insert operations")

    try:
      line_num = int(line_number)
    except (ValueError, TypeError) as exc:
      raise ValueError("Invalid line_number parameter") from exc

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if total_lines == 0:
      # Empty file: line_number must be 1
      if line_num != 1:
        raise ValueError(f"Line number {line_num} out of range (file has 0 lines)")
      return new_string + "\n"

    if line_num < 1 or line_num > total_lines:
      raise ValueError(f"Line number {line_num} out of range (file has {total_lines} lines)")

    # Ensure each line has a newline at the end for correct insertion
    # If the last line doesn't end with newline, add one
    if lines and not lines[-1].endswith("\n"):
      lines[-1] = lines[-1] + "\n"

    if operation == "insert_before":
      lines.insert(line_num - 1, new_string + "\n")
    else:  # insert_after
      lines.insert(line_num, new_string + "\n")

    return "".join(lines)

  def _do_delete(self, content: str, old_string: str, line_number: Any) -> str:
    """Delete content by old_string or by line number.

    If old_string is provided and non-empty, searches for and removes it.
    If line_number is provided, deletes that specific line.
    At least one of old_string or line_number must be provided.

    Args:
      content: Original file content.
      old_string: Text to search for and remove.
      line_number: 1-indexed line number to delete.

    Returns:
      Updated content string.

    Raises:
      ValueError: If neither old_string nor line_number provided,
        or if old_string not found / ambiguous,
        or if line_number out of range.
    """
    if line_number is not None:
      try:
        line_num = int(line_number)
      except (ValueError, TypeError) as exc:
        raise ValueError("Invalid line_number parameter") from exc

      lines = content.splitlines(keepends=True)
      total_lines = len(lines)

      if total_lines == 0:
        raise ValueError(f"Line number {line_num} out of range (file has 0 lines)")

      if line_num < 1 or line_num > total_lines:
        raise ValueError(f"Line number {line_num} out of range (file has {total_lines} lines)")

      del lines[line_num - 1]
      return "".join(lines)

    if old_string:
      require_exact = self._config.tools.update.require_exact_match
      occurrences = content.count(old_string)

      if occurrences == 0:
        raise ValueError("Search text not found")

      if require_exact and occurrences > 1:
        raise ValueError("Search text appears multiple times; ambiguous match")

      return content.replace(old_string, "", 1)

    raise ValueError("Either old_string or line_number is required for delete")
