"""Update tool implementation for Yoker.

Provides the ``update`` async function for editing existing file contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.

## Operations

The ``operation`` parameter (required) controls the edit mode:

- ``replace`` — Replace text matched by ``old_string`` with ``new_string``.
  Alternatively, provide ``line_range`` to replace a range of lines directly.
- ``insert`` — Insert ``new_string`` at ``line_number`` (content appears at
  that line, pushing existing lines down). Requires ``line_number``.
- ``append`` — Add ``new_string`` at the end of the file.
- ``delete`` — Delete text matched by ``old_string``, or a single line via
  ``line_number``, or a range of lines via ``line_range``.

## Matching modes

The ``replace`` and ``delete`` operations support two ways to identify the
target text:

1. **String match** (default): provide ``old_string`` to find the text to
   replace or delete. When ``require_exact_match`` is true (config default),
   the string must appear exactly once. When false, whitespace is normalized
   for matching, and the first match is used.

2. **Line-range match**: provide ``line_range`` as ``[start, end]``
   (1-indexed, inclusive) to replace or delete a range of lines without
   needing to match any text. This avoids ambiguous matches in large files.

The ``insert`` operation uses ``line_number`` to position new content.
The ``append`` operation requires no line number — content is added at end.
"""

import difflib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.builtin._validators import validate_update_diff_size
from yoker.config import UpdateToolConfig
from yoker.tools.annotations import Text, WritePath
from yoker.tools.context import ToolContext
from yoker.tools.diff import generate_diff
from yoker.tools.schema import ToolResult

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


def _truncate_diff(diff_lines: list[str], max_lines: int) -> tuple[str, bool, int]:
  """Truncate diff output to max_lines."""
  original_count = len(diff_lines)
  normalized_lines = [line if line.endswith("\n") else line + "\n" for line in diff_lines]

  if len(normalized_lines) <= max_lines:
    return "".join(normalized_lines), False, original_count

  return "".join(normalized_lines[:max_lines]), True, original_count


async def update(
  path: Annotated[str, WritePath("Path to the file to update")],
  ctx: ToolContext,
  operation: Annotated[
    str,
    Text(
      "File operation to execute. One of: 'replace', 'insert', 'append', 'delete'. "
      "When omitted, the operation is inferred from the other arguments: "
      "anchor + new_string → 'insert' (anchor-based), "
      "line_range + new_string → 'replace' (line-based), "
      "line_number + new_string → 'insert', old_string + new_string → 'replace', "
      "new_string only → 'append'. 'delete' is never inferred — "
      "it must always be specified explicitly."
    ),
  ] = "",
  old_string: Annotated[
    str,
    Text(
      "Text to find (required for replace and delete). Must match exactly when "
      "require_exact_match is true. When false, whitespace is normalized for "
      "matching and multiple matches use the first occurrence."
    ),
  ] = "",
  new_string: Annotated[
    str | None,
    Text(
      "Replacement or insertion text (required for replace, insert, and append). "
      "For replace: replaces old_string with this. For insert: the content to "
      "insert at line_number or relative to anchor. For append: the content to "
      "add at end of file. "
      "An empty string is a valid value (clears text for replace). When omitted "
      "(None), the operation cannot be inferred as replace/insert/append."
    ),
  ] = None,
  line_number: Annotated[
    int | None,
    Text(
      "Line number (1-indexed) for insert (required) or "
      "delete (optional: deletes that single line). Ignored for replace, append."
    ),
  ] = None,
  line_range: Annotated[
    list[int] | None,
    Text(
      "Line range [start, end] (1-indexed, inclusive) for line-based replace or "
      "delete. When provided, replaces or deletes those lines directly without "
      "string matching. Takes precedence over old_string for both operations."
    ),
  ] = None,
  anchor: Annotated[
    str | None,
    Text(
      "Anchor text for position-based insert: new_string is inserted directly "
      "after (position='after', default) or before (position='before') the "
      "unique occurrence of this text. The anchor itself is NOT modified — "
      "unlike replace, you do not need to retype it in new_string. The anchor "
      "must appear exactly once in the file; ambiguous anchors are rejected "
      "with all match line numbers. Takes precedence over line_number."
    ),
  ] = None,
  position: Annotated[
    str | None,
    Text(
      "Position of the insert relative to anchor: 'after' (default) or "
      "'before'. Only used together with anchor."
    ),
  ] = None,
  require_exact_match: Annotated[
    bool | None,
    Text(
      "Override the config default for exact match. When false, whitespace is "
      "normalized for matching and multiple matches use the first occurrence."
    ),
  ] = None,
) -> ToolResult:
  """Update an existing file by replacing, inserting, or deleting content.

  The ``operation`` parameter is optional and can be inferred from the
  other arguments when omitted:

  - **insert** (inferred when ``anchor`` + ``new_string`` provided):
    Anchor-based insert — ``new_string`` is placed directly after
    (``position='after'``, default) or before (``position='before'``) the
    unique occurrence of ``anchor``. The anchor text itself is NOT
    modified or retyped. The anchor must appear exactly once; ambiguous
    anchors are rejected with all match line numbers. This avoids both
    the "Search text not found" failures of replace-emulated inserts and
    the stale-line-number risk of line-based inserts.
  - **replace** (default when ``old_string`` + ``new_string`` provided, or
    ``line_range`` + ``new_string``):
    Replace text found via ``old_string`` with ``new_string``.
    Alternatively, provide ``line_range`` to replace a range of lines
    directly (takes precedence over ``old_string``).
  - **insert** (inferred when ``line_number`` + ``new_string`` provided):
    Insert ``new_string`` at ``line_number`` (content appears
    at that line, pushing existing lines down). Requires ``line_number``.
  - **append** (inferred when only ``new_string`` is provided):
    Add ``new_string`` at the end of the file.
  - **delete** (NEVER inferred — must always be explicit):
    Delete text found via ``old_string``. Alternatively,
    provide ``line_number`` to delete a single line, or ``line_range``
    to delete a range of lines.

  When ``operation`` is omitted and the arguments don't match any
  inference rule (e.g. ``old_string`` without ``new_string``), an error
  is returned suggesting ``operation='delete'``.

  When the operation is inferred, the success message states the inferred
  operation and advises providing an explicit ``operation`` next time.
  """
  update_config = ctx.config
  if not isinstance(update_config, UpdateToolConfig):
    logger.warning("update_invalid_config_type", config_type=type(update_config).__name__)
    return ToolResult(success=False, error="Invalid configuration for update tool")

  # Per-call override takes precedence over config default
  exact_match = (
    require_exact_match if require_exact_match is not None else update_config.require_exact_match
  )
  max_diff_size_kb = update_config.max_diff_size_kb

  if not isinstance(path, str) or not path.strip():
    logger.warning("update_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  # Infer operation when not explicitly provided.
  # Safe operations (replace, insert, append) can be inferred from arguments.
  # Delete is never inferred — it must always be explicit to prevent
  # accidental data loss from ambiguous arguments.
  operation_inferred = False
  if not operation:
    if anchor and new_string is not None:
      operation = "insert"
    elif line_range is not None and new_string is not None:
      operation = "replace"
    elif line_number is not None and new_string is not None:
      operation = "insert"
    elif old_string and new_string is not None:
      operation = "replace"
    elif new_string is not None and not old_string and line_range is None and line_number is None:
      operation = "append"
    else:
      # No inference possible — arguments don't match a safe operation.
      return ToolResult(
        success=False,
        error=(
          "Parameter 'operation' is required for this combination of arguments. "
          "Did you mean operation='delete'? Delete is never inferred — it must "
          "always be specified explicitly to prevent accidental data loss."
        ),
      )
    operation_inferred = True
    logger.info("update_operation_inferred", operation=operation)

  valid_operations = {"replace", "insert", "append", "delete"}
  if operation not in valid_operations:
    logger.warning("update_invalid_operation", operation=operation)
    return ToolResult(success=False, error="Invalid operation")

  if not isinstance(old_string, str):
    logger.warning("update_invalid_old_string_type", old_string_type=type(old_string).__name__)
    return ToolResult(success=False, error="Invalid old_string parameter")
  if new_string is not None and not isinstance(new_string, str):
    logger.warning("update_invalid_new_string_type", new_string_type=type(new_string).__name__)
    return ToolResult(success=False, error="Invalid new_string parameter")
  if anchor is not None and not isinstance(anchor, str):
    logger.warning("update_invalid_anchor_type", anchor_type=type(anchor).__name__)
    return ToolResult(success=False, error="Invalid anchor parameter")
  if position is not None and position not in ("after", "before"):
    logger.warning("update_invalid_position", position=position)
    return ToolResult(success=False, error="Invalid position: must be 'after' or 'before'")
  if anchor and operation and operation != "insert":
    logger.warning("update_anchor_wrong_operation", operation=operation)
    return ToolResult(
      success=False,
      error=f"anchor is only valid for operation='insert' (got '{operation}')",
    )
  # Normalize None to empty string for the execution path.
  # For delete, new_string is irrelevant; for replace, an explicit "" is valid.
  new_string = new_string or ""

  try:
    original_path = Path(path)
    if original_path.is_symlink():
      logger.warning("update_symlink_rejected", path=path)
      return ToolResult(success=False, error="Updating symlinks is not permitted")
  except (OSError, PermissionError):
    logger.warning("update_path_access_error", path=path)
    return ToolResult(success=False, error="Invalid path")

  try:
    resolved = Path(os.path.realpath(path))
  except (OSError, ValueError):
    logger.warning("update_invalid_path", path=path)
    return ToolResult(success=False, error="Invalid path")

  if not resolved.exists():
    logger.info("update_file_not_found", path=str(resolved))
    return ToolResult(success=False, error="File not found")
  if not resolved.is_file():
    logger.info("update_not_a_file", path=str(resolved))
    return ToolResult(success=False, error="Path is not a file")

  try:
    old_content = resolved.read_text(encoding="utf-8")
  except PermissionError:
    logger.warning("update_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except OSError:
    logger.error("update_read_error", path=str(resolved))
    return ToolResult(success=False, error="Error reading file")

  if max_diff_size_kb > 0:
    diff_size = len(new_string.encode("utf-8"))
    if diff_size > max_diff_size_kb * 1024:
      logger.info(
        "update_diff_size_exceeded",
        diff_size=diff_size,
        max_diff_size_kb=max_diff_size_kb,
      )
      return ToolResult(success=False, error="Diff size exceeds limit")

  try:
    if operation == "replace":
      result_content = _do_replace(old_content, old_string, new_string, line_range, exact_match)
    elif operation == "insert":
      result_content = _do_insert(old_content, line_number, new_string, anchor, position)
    elif operation == "append":
      result_content = _do_append(old_content, new_string)
    elif operation == "delete":
      result_content = _do_delete(old_content, old_string, line_number, line_range, exact_match)
    else:
      return ToolResult(success=False, error="Invalid operation")
  except ValueError as e:
    logger.info("update_validation_error", error=str(e))
    return ToolResult(success=False, error=str(e))

  try:
    temp_path = resolved.with_suffix(resolved.suffix + ".tmp")
    temp_path.write_text(result_content, encoding="utf-8")
    os.replace(str(temp_path), str(resolved))
    logger.info("update_success", path=str(resolved), operation=operation)

    content_metadata = _build_content_metadata(
      operation=operation,
      resolved_path=resolved,
      old_content=old_content,
      new_content=result_content,
      old_string=old_string,
      new_string=new_string,
      line_number=line_number,
      line_range=line_range,
      ctx=ctx,
    )

    if operation_inferred:
      result_message = (
        f"File updated successfully (operation inferred: '{operation}'). "
        "Next time, provide an explicit 'operation' to avoid inference."
      )
    else:
      result_message = "File updated successfully"

    return ToolResult(
      success=True,
      result=result_message,
      content_metadata=content_metadata,
    )
  except PermissionError:
    logger.warning("update_permission_denied_write", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except OSError as e:
    logger.error("update_write_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Error updating file")


def _build_content_metadata(
  operation: str,
  resolved_path: Path,
  old_content: str,
  new_content: str,
  old_string: str,
  new_string: str,
  line_number: Any,
  ctx: ToolContext | None,
  line_range: list[int] | None = None,
) -> dict[str, Any] | None:
  """Build content_metadata for ToolResult."""
  # Get content display config from context or use defaults
  if ctx is not None:
    content_display = ctx.shared.content_display
  else:
    # Fallback defaults
    from yoker.config import ContentDisplayConfig

    content_display = ContentDisplayConfig()

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
      line_range=line_range,
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
      line_range=line_range,
    )

  return _build_content_or_diff_metadata(
    operation=operation,
    resolved_path=resolved_path,
    old_content=old_content,
    new_content=new_content,
    old_string=old_string,
    new_string=new_string,
    line_number=line_number,
    line_range=line_range,
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
  line_range: list[int] | None = None,
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
  elif operation in ("insert", "append"):
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
  line_range: list[int] | None = None,
) -> dict[str, Any]:
  """Build content or diff metadata for content verbosity mode."""
  if content_display is None:
    from yoker.config import ContentDisplayConfig

    content_display = ContentDisplayConfig()

  if operation == "replace":
    if use_diff and content_display.show_diff_for_updates:
      old_lines = old_content.splitlines(keepends=True)
      new_lines = new_content.splitlines(keepends=True)

      diff_text = generate_diff(old_content, new_content, resolved_path.name)

      # Pass full diff to the UI — truncation (middle-collapse) is handled
      # by the UI layer using ContentDisplayConfig settings.
      metadata = {
        "lines_modified": 1,
        "old_content_lines": len(old_lines),
        "new_content_lines": len(new_lines),
      }

      return {
        "operation": operation,
        "path": str(resolved_path),
        "content_type": "text/x-diff",
        "content": diff_text,
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
  elif operation in ("insert", "append"):
    line_num = int(line_number) if line_number is not None else 0
    old_lines = old_content.splitlines(keepends=True)
    if operation == "append":
      line_num = len(old_lines)
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
      diff_text = generate_diff(old_content, new_content, resolved_path.name)

      del_metadata = {
        "line_number": int(line_number) if line_number is not None else 0,
        "deleted_lines": len(old_string.splitlines()) if old_string else 1,
        "deleted_content": old_string,
      }

      return {
        "operation": operation,
        "path": str(resolved_path),
        "content_type": "text/x-diff",
        "content": diff_text,
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
  line_range: list[int] | None,
  require_exact_match: bool,
) -> str:
  """Replace content by string match or line range.

  When ``line_range`` is provided, replaces lines start..end (1-indexed,
  inclusive) with ``new_string``, ignoring ``old_string`` entirely.

  When ``line_range`` is None, uses ``old_string`` to find and replace.
  With ``require_exact_match=True``, the string must appear exactly once.
  With ``require_exact_match=False``, whitespace is normalized for matching.
  """
  if line_range is not None:
    return _replace_line_range(old_content, line_range, new_string)

  if not old_string:
    raise ValueError("Either old_string or line_range is required for replace")

  return _replace_string(old_content, old_string, new_string, require_exact_match)


def _replace_line_range(
  old_content: str,
  line_range: list[int],
  new_string: str,
) -> str:
  """Replace a range of lines with new_string."""
  if len(line_range) != 2:
    raise ValueError("line_range must be a [start, end] pair")

  start, end = line_range
  if not isinstance(start, int) or not isinstance(end, int):
    raise ValueError("line_range values must be integers")

  if start < 1:
    raise ValueError(f"line_range start {start} must be >= 1")
  if end < start:
    raise ValueError(f"line_range end {end} must be >= start {start}")

  lines = old_content.splitlines(keepends=True)
  total = len(lines)

  if total == 0:
    raise ValueError(f"Line range [{start}, {end}] out of range (file has 0 lines)")
  if start > total:
    raise ValueError(f"line_range start {start} out of range (file has {total} lines)")

  # Clamp end to total — allows replacing from start to end-of-file
  actual_end = min(end, total)

  if lines and not lines[-1].endswith("\n") and actual_end == total:
    lines[-1] = lines[-1] + "\n"

  replacement = new_string
  if replacement and not replacement.endswith("\n"):
    replacement = replacement + "\n"

  new_lines = lines[: start - 1] + [replacement] + lines[actual_end:]
  return "".join(new_lines)


def _replace_string(
  old_content: str,
  old_string: str,
  new_string: str,
  require_exact_match: bool,
) -> str:
  """Replace old_string with new_string, optionally with fuzzy matching."""
  if require_exact_match:
    occurrences = old_content.count(old_string)

    if occurrences == 0:
      raise ValueError(_not_found_error(old_content, old_string))

    if occurrences > 1:
      raise ValueError(_multiple_matches_error(old_content, old_string))

    return old_content.replace(old_string, new_string, 1)

  # Whitespace-insensitive matching: find the first occurrence where
  # whitespace-normalized content matches the normalized search string.
  return _fuzzy_replace(old_content, old_string, new_string)


def _fuzzy_replace(old_content: str, old_string: str, new_string: str) -> str:
  """Replace first whitespace-insensitive match of old_string."""
  import re

  # Build a regex that treats any whitespace run in old_string as \s+
  escaped = re.escape(old_string)
  pattern = re.sub(r"\\ ", r"\\s+", escaped)
  # Also normalize: any sequence of escaped spaces/tabs -> \s+
  pattern = re.sub(r"(?:\\ )+", r"\\s+", pattern)

  match = re.search(pattern, old_content)
  if match:
    return old_content[: match.start()] + new_string + old_content[match.end() :]

  raise ValueError(_not_found_error(old_content, old_string))


def _do_insert(
  old_content: str,
  line_number: Any,
  new_string: str,
  anchor: str | None = None,
  position: str | None = None,
) -> str:
  """Insert new_string at a specific line or relative to an anchor.

  Two positioning modes:

  - **Anchor-based** (``anchor`` provided): ``new_string`` is inserted
    directly after (default) or before the unique occurrence of
    ``anchor``. The anchor must appear exactly once — ambiguous anchors
    are rejected with all match line numbers (fail-loud, never
    first-match-silently). The anchor text itself is not modified.
    Takes precedence over ``line_number``.
  - **Line-based** (``line_number``): the new content is inserted
    *before* the existing line at ``line_number``, so it appears at that
    line number in the resulting file.
  """
  if anchor:
    return _insert_by_anchor(old_content, anchor, new_string, position or "after")

  if line_number is None:
    raise ValueError("line_number is required for insert operations (or provide anchor)")

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

  lines.insert(line_num - 1, new_string + "\n")
  return "".join(lines)


def _insert_by_anchor(
  old_content: str,
  anchor: str,
  new_string: str,
  position: str,
) -> str:
  """Insert new_string directly after or before the unique anchor occurrence.

  Matching mirrors ``replace`` semantics: exact substring match first, then
  a whitespace-normalized (fuzzy) fallback restricted to whole-line matches
  (every line of the anchor must fuzzy-match a consecutive run of file
  lines). The anchor must resolve to exactly one location — ambiguous
  anchors are rejected with match line numbers (fail-loud).

  Insertion points are line-aligned: 'before' inserts at the start of the
  anchor's first line, 'after' inserts at the start of the line following
  the anchor's last line. The new content always ends with a newline.
  """
  lines = old_content.splitlines(keepends=True)
  anchor_lines = anchor.strip("\n").splitlines()

  # --- Locate the anchor: unique exact line-run, else fuzzy line-run ----
  match_start_line = _find_unique_anchor_line(lines, anchor_lines)

  if match_start_line is None:
    raise ValueError(_not_found_error(old_content, anchor))

  # --- Compute the insertion point (line index) --------------------------
  if position == "before":
    insert_line = match_start_line
  else:  # "after"
    insert_line = match_start_line + len(anchor_lines)
    # Skip the anchor's trailing blank remainder if the exact match ended
    # mid-content — insert after the anchor's last line only.
    insert_line = min(insert_line, len(lines))

  insertion = new_string if new_string.endswith("\n") else new_string + "\n"

  # Mirror line-based insert: if the file's last line lacks a trailing
  # newline, normalize it first so the insertion always starts on a fresh
  # line (a mid-line splice would corrupt e.g. '  return 2' + new code).
  if lines and not lines[-1].endswith("\n"):
    lines[-1] = lines[-1] + "\n"

  return "".join(lines[:insert_line]) + insertion + "".join(lines[insert_line:])


def _find_unique_anchor_line(lines: list[str], anchor_lines: list[str]) -> int | None:
  """Find the unique 0-indexed start line whose line-run matches anchor_lines.

  Exact matching: every anchor line must appear as a substring of the
  corresponding file line. If zero exact matches, fall back to
  whitespace-normalized matching. Returns the 0-indexed start line of the
  unique match, or None. Raises ValueError on ambiguity.
  """

  def find_runs(normalize: Any) -> list[int]:
    runs: list[int] = []
    for start in range(len(lines) - len(anchor_lines) + 1):
      if all(
        normalize(anchor_lines[k]) in normalize(lines[start + k]) for k in range(len(anchor_lines))
      ):
        runs.append(start)
    return runs

  exact = find_runs(lambda s: s)
  if len(exact) == 1:
    return exact[0]
  if len(exact) > 1:
    raise ValueError(_multiple_matches_error("".join(lines), anchor_lines[0]))

  # Fuzzy fallback: whitespace-normalized, whole-line run matching.
  def norm(text: str) -> str:
    return " ".join(text.split())

  fuzzy = find_runs(norm)
  if len(fuzzy) == 1:
    return fuzzy[0]
  if len(fuzzy) > 1:
    raise ValueError(
      f"Ambiguous anchor: whitespace-normalized text appears {len(fuzzy)} times. "
      + _multiple_matches_error("".join(lines), anchor_lines[0])
    )
  return None


def _do_append(
  old_content: str,
  new_string: str,
) -> str:
  """Append new_string at the end of the file."""
  if not old_content:
    return new_string + "\n"

  content = old_content
  if not content.endswith("\n"):
    content = content + "\n"
  return content + new_string + "\n"


def _do_delete(
  old_content: str,
  old_string: str,
  line_number: Any,
  line_range: list[int] | None,
  require_exact_match: bool,
) -> str:
  """Delete content by old_string, line number, or line range."""
  if line_range is not None:
    return _delete_line_range(old_content, line_range)

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
    if require_exact_match:
      occurrences = old_content.count(old_string)
      if occurrences == 0:
        raise ValueError(_not_found_error(old_content, old_string))
      if occurrences > 1:
        raise ValueError(_multiple_matches_error(old_content, old_string))
      return old_content.replace(old_string, "", 1)

    # Fuzzy delete
    import re

    escaped = re.escape(old_string)
    pattern = re.sub(r"(?:\\ )+", r"\\s+", escaped)
    match = re.search(pattern, old_content)
    if match:
      return old_content[: match.start()] + old_content[match.end() :]
    raise ValueError(_not_found_error(old_content, old_string))

  raise ValueError("Either old_string, line_number, or line_range is required for delete")


def _delete_line_range(old_content: str, line_range: list[int]) -> str:
  """Delete a range of lines."""
  if len(line_range) != 2:
    raise ValueError("line_range must be a [start, end] pair")

  start, end = line_range
  if not isinstance(start, int) or not isinstance(end, int):
    raise ValueError("line_range values must be integers")

  if start < 1:
    raise ValueError(f"line_range start {start} must be >= 1")
  if end < start:
    raise ValueError(f"line_range end {end} must be >= start {start}")

  lines = old_content.splitlines(keepends=True)
  total = len(lines)

  if total == 0:
    raise ValueError(f"Line range [{start}, {end}] out of range (file has 0 lines)")
  if start > total:
    raise ValueError(f"line_range start {start} out of range (file has {total} lines)")

  actual_end = min(end, total)
  del lines[start - 1 : actual_end]
  return "".join(lines)


def _not_found_error(old_content: str, old_string: str) -> str:
  """Build a helpful 'not found' error message with closest match context."""
  search_lines = old_string.strip().splitlines()
  if not search_lines:
    return "Search text not found (empty search)"

  first_search_line = search_lines[0].strip()
  content_lines = old_content.splitlines()

  # Find the closest matching line using difflib
  best_ratio = 0.0
  best_line_num = 0
  best_line = ""
  for i, line in enumerate(content_lines):
    ratio = difflib.SequenceMatcher(None, first_search_line, line.strip()).ratio()
    if ratio > best_ratio:
      best_ratio = ratio
      best_line_num = i + 1
      best_line = line

  if best_ratio > 0.5:
    return (
      f"Search text not found. Closest match at line {best_line_num} "
      f"({best_ratio:.0%} similarity): {best_line.strip()!r}"
    )
  return "Search text not found"


def _multiple_matches_error(old_content: str, old_string: str) -> str:
  """Build a helpful 'multiple matches' error with line numbers."""
  content_lines = old_content.splitlines(keepends=True)
  first_search_line = old_string.strip().splitlines()[0] if old_string.strip() else ""

  match_lines = []
  for i, line in enumerate(content_lines):
    if first_search_line and first_search_line in line:
      match_lines.append(i + 1)

  if match_lines:
    lines_str = ", ".join(str(n) for n in match_lines[:10])
    suffix = f" ... and {len(match_lines) - 10} more" if len(match_lines) > 10 else ""
    return (
      f"Search text appears multiple times; ambiguous match. "
      f"Found at line(s): {lines_str}{suffix}. "
      f"Use line_range for line-based replace, or provide more context in old_string."
    )
  return "Search text appears multiple times; ambiguous match"


update.__yoker_validators__ = [validate_update_diff_size]  # type: ignore[attr-defined]


__all__ = ["update"]
