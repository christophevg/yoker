"""Update tool implementation for Yoker.

Provides the ``make_update_tool`` factory that returns a callable for
editing existing file contents. Guardrails are enforced centrally by the
harness based on the schema's ``path`` annotation.
"""

import difflib
import os
from pathlib import Path
from typing import Annotated, Any

from structlog import get_logger

from yoker.annotations import Path as PathArg
from yoker.annotations import Text
from yoker.config import Config
from yoker.tools.base import ToolResult

log = get_logger(__name__)


def _truncate_diff(diff_lines: list[str], max_lines: int) -> tuple[str, bool, int]:
  """Truncate diff output to max_lines."""
  original_count = len(diff_lines)
  normalized_lines = [line if line.endswith("\n") else line + "\n" for line in diff_lines]

  if len(normalized_lines) <= max_lines:
    return "".join(normalized_lines), False, original_count

  return "".join(normalized_lines[:max_lines]), True, original_count


def make_update_tool(config: Config | None = None) -> Any:
  """Create the update tool callable."""
  resolved_config = config or Config()

  async def update(
    path: Annotated[str, PathArg("Path to the file to update")],
    operation: str,
    old_string: Annotated[
      str,
      Text(
        "Text to find (required for replace and delete). Must match exactly when require_exact_match is true."
      ),
    ] = "",
    new_string: Annotated[
      str, Text("Replacement or insertion text (required for replace and insert)")
    ] = "",
    line_number: int | None = None,
  ) -> ToolResult:
    """Update an existing file by replacing, inserting, or deleting content."""
    if not isinstance(path, str) or not path.strip():
      log.warning("update_invalid_path_type", path_type=type(path).__name__)
      return ToolResult(success=False, error="Invalid path parameter")

    valid_operations = {"replace", "insert_before", "insert_after", "delete"}
    if operation not in valid_operations:
      log.warning("update_invalid_operation", operation=operation)
      return ToolResult(success=False, error="Invalid operation")

    if not isinstance(old_string, str):
      log.warning("update_invalid_old_string_type", old_string_type=type(old_string).__name__)
      return ToolResult(success=False, error="Invalid old_string parameter")
    if not isinstance(new_string, str):
      log.warning("update_invalid_new_string_type", new_string_type=type(new_string).__name__)
      return ToolResult(success=False, error="Invalid new_string parameter")

    try:
      original_path = Path(path)
      if original_path.is_symlink():
        log.warning("update_symlink_rejected", path=path)
        return ToolResult(success=False, error="Updating symlinks is not permitted")
    except (OSError, PermissionError):
      log.warning("update_path_access_error", path=path)
      return ToolResult(success=False, error="Invalid path")

    try:
      resolved = Path(os.path.realpath(path))
    except (OSError, ValueError):
      log.warning("update_invalid_path", path=path)
      return ToolResult(success=False, error="Invalid path")

    if not resolved.exists():
      log.info("update_file_not_found", path=str(resolved))
      return ToolResult(success=False, error="File not found")
    if not resolved.is_file():
      log.info("update_not_a_file", path=str(resolved))
      return ToolResult(success=False, error="Path is not a file")

    try:
      old_content = resolved.read_text(encoding="utf-8")
    except PermissionError:
      log.warning("update_permission_denied", path=str(resolved))
      return ToolResult(success=False, error="Permission denied")
    except OSError:
      log.error("update_read_error", path=str(resolved))
      return ToolResult(success=False, error="Error reading file")

    update_config = resolved_config.tools.update
    max_diff_size_kb = update_config.max_diff_size_kb
    if max_diff_size_kb > 0:
      diff_size = len(new_string.encode("utf-8"))
      if diff_size > max_diff_size_kb * 1024:
        log.info(
          "update_diff_size_exceeded",
          diff_size=diff_size,
          max_diff_size_kb=max_diff_size_kb,
        )
        return ToolResult(success=False, error="Diff size exceeds limit")

    try:
      if operation == "replace":
        result_content = _do_replace(old_content, old_string, new_string, resolved_config)
      elif operation in ("insert_before", "insert_after"):
        result_content = _do_insert(old_content, operation, line_number, new_string)
      elif operation == "delete":
        result_content = _do_delete(old_content, old_string, line_number, resolved_config)
      else:
        return ToolResult(success=False, error="Invalid operation")
    except ValueError as e:
      log.info("update_validation_error", error=str(e))
      return ToolResult(success=False, error=str(e))

    try:
      temp_path = resolved.with_suffix(resolved.suffix + ".tmp")
      temp_path.write_text(result_content, encoding="utf-8")
      os.replace(str(temp_path), str(resolved))
      log.info("update_success", path=str(resolved), operation=operation)

      content_metadata = _build_content_metadata(
        operation=operation,
        resolved_path=resolved,
        old_content=old_content,
        new_content=result_content,
        old_string=old_string,
        new_string=new_string,
        line_number=line_number,
        config=resolved_config,
      )

      return ToolResult(
        success=True,
        result="File updated successfully",
        content_metadata=content_metadata,
      )
    except PermissionError:
      log.warning("update_permission_denied_write", path=str(resolved))
      return ToolResult(success=False, error="Permission denied")
    except OSError as e:
      log.error("update_write_error", path=str(resolved), error=str(e))
      return ToolResult(success=False, error="Error updating file")

  return update


def _build_content_metadata(
  operation: str,
  resolved_path: Path,
  old_content: str,
  new_content: str,
  old_string: str,
  new_string: str,
  line_number: Any,
  config: Config,
) -> dict[str, Any] | None:
  """Build content_metadata for ToolResult."""
  content_display = config.tools.content_display

  if content_display.verbosity == "silent":
    return None

  if content_display.show_diff_for_updates:
    return _build_content_or_diff_metadata(
      operation=operation,
      resolved_path=resolved_path,
      old_content=old_content,
      new_content=new_content,
      old_string=old_string,
      new_string=new_string,
      line_number=line_number,
      content_display=content_display,
    )

  if content_display.verbosity == "summary":
    return _build_summary_metadata(
      operation=operation,
      resolved_path=resolved_path,
      old_content=old_content,
      new_content=new_content,
      old_string=old_string,
      new_string=new_string,
      line_number=line_number,
    )

  return _build_content_or_diff_metadata(
    operation=operation,
    resolved_path=resolved_path,
    old_content=old_content,
    new_content=new_content,
    old_string=old_string,
    new_string=new_string,
    line_number=line_number,
    use_diff=False,
    content_display=content_display,
  )


def _build_summary_metadata(
  operation: str,
  resolved_path: Path,
  old_content: str,
  new_content: str,
  old_string: str,
  new_string: str,
  line_number: Any,
) -> dict[str, Any]:
  """Build summary metadata for summary verbosity mode."""
  old_lines = len(old_content.splitlines()) if old_content else 0
  new_lines = len(new_content.splitlines()) if new_content else 0

  if operation == "replace":
    return {
      "operation": operation,
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "lines_modified": 1,
        "old_content_lines": old_lines,
        "new_content_lines": new_lines,
        "old_string": old_string,
        "new_string": new_string,
      },
    }
  elif operation in ("insert_before", "insert_after"):
    line_num = int(line_number) if line_number is not None else 0
    return {
      "operation": operation,
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "line_number": line_num,
        "inserted_lines": len(new_string.splitlines()),
        "new_content_lines": new_lines,
        "inserted_content": new_string,
      },
    }
  else:  # delete
    return {
      "operation": operation,
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "line_number": int(line_number) if line_number is not None else 0,
        "deleted_lines": len(old_string.splitlines()) if old_string else 1,
        "deleted_content": old_string,
      },
    }


def _build_content_or_diff_metadata(
  operation: str,
  resolved_path: Path,
  old_content: str,
  new_content: str,
  old_string: str,
  new_string: str,
  line_number: Any,
  use_diff: bool = True,
  content_display: Any | None = None,
) -> dict[str, Any]:
  """Build content or diff metadata for content verbosity mode."""
  if content_display is None:
    from yoker.config import Config

    content_display = Config().tools.content_display

  if operation == "replace":
    if use_diff and content_display.show_diff_for_updates:
      old_lines = old_content.splitlines(keepends=True)
      new_lines = new_content.splitlines(keepends=True)

      diff_lines = list(
        difflib.unified_diff(
          old_lines,
          new_lines,
          fromfile="before",
          tofile="after",
        )
      )
      diff_content, was_truncated, original_count = _truncate_diff(
        diff_lines,
        content_display.max_diff_lines,
      )

      metadata = {
        "lines_modified": 1,
        "old_content_lines": len(old_lines),
        "new_content_lines": len(new_lines),
      }

      if was_truncated:
        metadata["truncated"] = True
        metadata["original_diff_lines"] = original_count

      return {
        "operation": operation,
        "path": str(resolved_path),
        "content_type": "text/x-diff",
        "content": diff_content,
        "metadata": metadata,
      }
    else:
      return {
        "operation": operation,
        "path": str(resolved_path),
        "content_type": "text/plain",
        "content": new_content,
        "metadata": {
          "lines_modified": 1,
          "old_content_lines": len(old_content.splitlines()) if old_content else 0,
          "new_content_lines": len(new_content.splitlines()) if new_content else 0,
        },
      }
  elif operation in ("insert_before", "insert_after"):
    line_num = int(line_number) if line_number is not None else 0
    old_lines = old_content.splitlines(keepends=True)
    context_before = old_lines[max(0, line_num - 3) : line_num]
    context_after = old_lines[line_num : min(len(old_lines), line_num + 3)]

    return {
      "operation": operation,
      "path": str(resolved_path),
      "content_type": "text/plain",
      "content": new_string,
      "metadata": {
        "line_number": line_num,
        "inserted_lines": len(new_string.splitlines()),
        "lines_before": len(context_before),
        "lines_after": len(context_after),
        "context_before": "".join(context_before),
        "context_after": "".join(context_after),
      },
    }
  else:  # delete
    if use_diff and content_display.show_diff_for_updates:
      old_lines = old_content.splitlines(keepends=True)
      new_lines = new_content.splitlines(keepends=True)

      diff_lines = list(
        difflib.unified_diff(
          old_lines,
          new_lines,
          fromfile="before",
          tofile="after",
        )
      )
      diff_content, was_truncated, original_count = _truncate_diff(
        diff_lines,
        content_display.max_diff_lines,
      )

      del_metadata = {
        "line_number": int(line_number) if line_number is not None else 0,
        "deleted_lines": len(old_string.splitlines()) if old_string else 1,
        "deleted_content": old_string,
      }

      if was_truncated:
        del_metadata["truncated"] = True
        del_metadata["original_diff_lines"] = original_count

      return {
        "operation": operation,
        "path": str(resolved_path),
        "content_type": "text/x-diff",
        "content": diff_content,
        "metadata": del_metadata,
      }
    else:
      return {
        "operation": operation,
        "path": str(resolved_path),
        "content_type": "text/plain",
        "content": old_string,
        "metadata": {
          "line_number": int(line_number) if line_number is not None else 0,
          "deleted_lines": len(old_string.splitlines()) if old_string else 1,
        },
      }


def _do_replace(
  old_content: str,
  old_string: str,
  new_string: str,
  config: Config,
) -> str:
  """Replace old_string with new_string in content."""
  require_exact = config.tools.update.require_exact_match
  occurrences = old_content.count(old_string)

  if occurrences == 0:
    raise ValueError("Search text not found")

  if require_exact and occurrences > 1:
    raise ValueError("Search text appears multiple times; ambiguous match")

  return old_content.replace(old_string, new_string, 1)


def _do_insert(
  old_content: str,
  operation: str,
  line_number: Any,
  new_string: str,
) -> str:
  """Insert new_string before or after a specific line."""
  if line_number is None:
    raise ValueError("line_number is required for insert operations")

  try:
    line_num = int(line_number)
  except (ValueError, TypeError) as exc:
    raise ValueError("Invalid line_number parameter") from exc

  lines = old_content.splitlines(keepends=True)
  total_lines = len(lines)

  if total_lines == 0:
    if line_num != 1:
      raise ValueError(f"Line number {line_num} out of range (file has 0 lines)")
    return new_string + "\n"

  if line_num < 1 or line_num > total_lines:
    raise ValueError(f"Line number {line_num} out of range (file has {total_lines} lines)")

  if lines and not lines[-1].endswith("\n"):
    lines[-1] = lines[-1] + "\n"

  if operation == "insert_before":
    lines.insert(line_num - 1, new_string + "\n")
  else:  # insert_after
    lines.insert(line_num, new_string + "\n")

  return "".join(lines)


def _do_delete(
  old_content: str,
  old_string: str,
  line_number: Any,
  config: Config,
) -> str:
  """Delete content by old_string or by line number."""
  if line_number is not None:
    try:
      line_num = int(line_number)
    except (ValueError, TypeError) as exc:
      raise ValueError("Invalid line_number parameter") from exc

    lines = old_content.splitlines(keepends=True)
    total_lines = len(lines)

    if total_lines == 0:
      raise ValueError(f"Line number {line_num} out of range (file has 0 lines)")

    if line_num < 1 or line_num > total_lines:
      raise ValueError(f"Line number {line_num} out of range (file has {total_lines} lines)")

    del lines[line_num - 1]
    return "".join(lines)

  if old_string:
    require_exact = config.tools.update.require_exact_match
    occurrences = old_content.count(old_string)

    if occurrences == 0:
      raise ValueError("Search text not found")

    if require_exact and occurrences > 1:
      raise ValueError("Search text appears multiple times; ambiguous match")

    return old_content.replace(old_string, "", 1)

  raise ValueError("Either old_string or line_number is required for delete")


__all__ = ["make_update_tool"]
