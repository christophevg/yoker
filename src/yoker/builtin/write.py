"""Write tool implementation for Yoker.

Provides the ``write`` async function for writing file contents.
Guardrails are enforced centrally by the harness based on the schema's
``path`` annotation.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from structlog import get_logger

from yoker.builtin._validators import validate_write_content_size
from yoker.config import WriteToolConfig
from yoker.tools.annotations import Text, WritePath
from yoker.tools.context import ToolContext
from yoker.tools.schema import ApprovalPrompt, ToolResult

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


def _is_binary(content: str) -> bool:
  """Check if content appears to be binary."""
  check_size = min(len(content), 8192)
  return "\x00" in content[:check_size]


def _truncate_content(
  content: str,
  max_lines: int,
  max_bytes: int,
) -> tuple[str, bool, int, int]:
  """Truncate content based on max lines and max bytes."""
  original_bytes = len(content.encode("utf-8"))
  lines = content.splitlines(keepends=True)
  original_lines_count = len(lines)

  if len(lines) > max_lines:
    lines = lines[:max_lines]
    was_truncated = True
  else:
    was_truncated = False

  truncated_content = "".join(lines)
  truncated_bytes = len(truncated_content.encode("utf-8"))

  if truncated_bytes > max_bytes:
    truncated_content = truncated_content[:max_bytes]
    was_truncated = True

  return truncated_content, was_truncated, original_lines_count, original_bytes


async def write(
  path: Annotated[str, WritePath("Path to the file to write")],
  content: Annotated[str, Text("Content to write to the file")],
  ctx: ToolContext,
  create_parents: bool = True,
) -> ToolResult:
  """Write content to a file.

  If the parent directory does not exist:
    - With create_parents=True (default): all parent directories are
      created automatically (equivalent to mkdir -p).
    - With create_parents=False: the operation fails with
      "Parent directory does not exist" — the directory structure must
      already exist (e.g. created with the mkdir tool).

  Overwriting existing files is controlled by the allow_overwrite setting
  in the write tool configuration (default: not permitted).
  """
  # Config values come from ctx.config (WriteToolConfig with defaults)
  write_config = ctx.config
  if not isinstance(write_config, WriteToolConfig):
    logger.warning("write_invalid_config_type", config_type=type(write_config).__name__)
    return ToolResult(success=False, error="Invalid configuration for write tool")
  allow_overwrite = write_config.allow_overwrite

  previous_content: str | None = None

  if not isinstance(path, str) or not path.strip():
    logger.warning("write_invalid_path_type", path_type=type(path).__name__)
    return ToolResult(success=False, error="Invalid path parameter")

  if not isinstance(content, str):
    logger.warning("write_invalid_content_type", content_type=type(content).__name__)
    return ToolResult(success=False, error="Invalid content parameter")

  original_path = Path(path)
  if original_path.is_symlink():
    logger.warning("write_symlink_rejected", path=path)
    return ToolResult(success=False, error="Writing to symlinks is not permitted")

  try:
    resolved = Path(os.path.realpath(path))
  except (OSError, ValueError):
    logger.warning("write_invalid_path", path=path)
    return ToolResult(success=False, error="Invalid path")

  is_overwrite = resolved.exists()
  if is_overwrite:
    if not allow_overwrite:
      logger.info("write_overwrite_blocked", path=str(resolved))
      return ToolResult(success=False, error="File already exists and overwrite is not permitted")
    # Capture pre-write content for the LLM-facing result diff (#62).
    try:
      previous_content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
      previous_content = None

  parent = resolved.parent
  if not parent.exists():
    if create_parents:
      try:
        parent.mkdir(parents=True, exist_ok=True)
        logger.info("write_created_parents", path=str(parent))
      except OSError as e:
        logger.error("write_create_parents_failed", path=str(parent), error=str(e))
        return ToolResult(success=False, error="Failed to create parent directories")
    else:
      logger.info("write_parent_missing", path=str(resolved))
      return ToolResult(success=False, error="Parent directory does not exist")

  try:
    resolved.write_text(content, encoding="utf-8")
    logger.info("write_success", path=str(resolved), bytes=len(content.encode("utf-8")))

    content_metadata = _build_content_metadata(
      content=content,
      resolved_path=resolved,
      is_overwrite=is_overwrite,
      ctx=ctx,
    )

    result_message = _build_write_result_message(content, is_overwrite, previous_content, resolved)

    return ToolResult(
      success=True,
      result=result_message,
      content_metadata=content_metadata,
    )
  except PermissionError:
    logger.warning("write_permission_denied", path=str(resolved))
    return ToolResult(success=False, error="Permission denied")
  except OSError as e:
    logger.error("write_os_error", path=str(resolved), error=str(e))
    return ToolResult(success=False, error="Error writing file")


def _build_content_metadata(
  content: str,
  resolved_path: Path,
  is_overwrite: bool,
  ctx: ToolContext | None,
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

  is_binary = _is_binary(content)
  if is_binary:
    byte_size = len(content.encode("utf-8"))
    return {
      "operation": "write",
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "lines": 0,
        "bytes": byte_size,
        "is_new_file": not is_overwrite,
        "is_overwrite": is_overwrite,
        "is_binary": True,
      },
    }

  lines = content.splitlines()
  line_count = len(lines)
  byte_size = len(content.encode("utf-8"))
  is_empty = line_count == 0

  if content_display.verbosity == "summary":
    return {
      "operation": "write",
      "path": str(resolved_path),
      "content_type": "application/x-summary",
      "content": None,
      "metadata": {
        "lines": line_count,
        "bytes": byte_size,
        "is_new_file": not is_overwrite,
        "is_overwrite": is_overwrite,
        "is_empty": is_empty,
      },
    }

  # Pass full content to the UI — truncation (middle-collapse) is handled
  # by the UI layer using ContentDisplayConfig settings.
  metadata: dict[str, Any] = {
    "lines": line_count,
    "bytes": byte_size,
    "is_new_file": not is_overwrite,
    "is_overwrite": is_overwrite,
    "is_empty": is_empty,
  }

  return {
    "operation": "write",
    "path": str(resolved_path),
    "content_type": "text/plain",
    "content": content,
    "metadata": metadata,
  }


write.__yoker_validators__ = [validate_write_content_size]  # type: ignore[attr-defined]


def _approval_prompt(tool_args: dict[str, Any]) -> ApprovalPrompt:
  """Build the approval prompt for writing to a write-protected file.

  Diffs the current file content (if any) against the new content. New
  files produce an all-additions diff. Mirrors the framework's generic
  ``write`` preview so the user sees exactly what the overwrite would do.
  """
  from yoker.tools.diff import generate_diff

  path = tool_args.get("path", "")
  new_content = tool_args.get("content", "")
  try:
    old_content = Path(path).read_text(encoding="utf-8")
  except OSError:
    old_content = ""
  return ApprovalPrompt(
    label=path,
    preview=generate_diff(old_content, new_content, Path(path).name),
  )


write.__yoker_approval__ = _approval_prompt  # type: ignore[attr-defined]


def _build_write_result_message(
  content: str,
  is_overwrite: bool,
  previous_content: str | None,
  resolved_path: Path,
) -> str:
  """Build the LLM-facing result string for a successful write (#62).

  - **New file**: stat only — a diff against empty would just echo the
    content the model already has in context.
  - **Overwrite**: stat line plus a compact unified diff of the applied
    change (capped), so the model can verify the edit without a
    read-after-write round trip. Same verification channel as `update`.
  """
  lines = content.splitlines()
  stat = f"File written successfully ({len(lines)} lines, {len(content.encode('utf-8'))} bytes)"

  if not is_overwrite or previous_content is None:
    return stat

  return _append_result_diff(stat, previous_content, content, resolved_path.name)


def _append_result_diff(
  result_message: str,
  old_content: str,
  new_content: str,
  filename: str,
) -> str:
  """Append a compact diff of the applied change to the result string.

  Shared with the update tool via the same pattern: one stat line
  (changed-line counts) plus the unified diff body, capped at
  ``_RESULT_DIFF_MAX_LINES`` lines with a trailing summary when truncated.
  Stats stay present even when the body is truncated, so a
  larger-than-expected change remains auditable.
  """
  from yoker.tools.diff import generate_diff

  diff_text = generate_diff(old_content, new_content, filename)
  diff_lines = diff_text.splitlines()

  added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
  removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

  if added == 0 and removed == 0:
    return f"{result_message} (no content change)"

  stat = f"{result_message} (+{added} \u2212{removed})"

  if len(diff_lines) <= _RESULT_DIFF_MAX_LINES:
    diff_body = diff_text.rstrip("\n")
    return f"{stat}\n{diff_body}"

  body = "\n".join(diff_lines[:_RESULT_DIFF_MAX_LINES])
  omitted = len(diff_lines) - _RESULT_DIFF_MAX_LINES
  return f"{stat}\n{body}\n... {omitted} more diff lines"


_RESULT_DIFF_MAX_LINES = 60


__all__ = ["write"]
