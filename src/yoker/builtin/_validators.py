"""Tool-specific validators for builtin tools.

These validators check operational constraints (file size, content size,
diff size, directory depth) after the generic guardrail has passed.
They are attached to tool callables via ``__yoker_validators__`` and
discovered by ``build_tool_spec`` during introspection.

Each validator has the signature:
    (tool_args: dict[str, Any], config: ToolConfig) -> ValidationResult

The validator receives the full tool arguments and the tool-specific
config, and returns a ValidationResult indicating whether the arguments
satisfy the tool's operational constraints.
"""

import os
from pathlib import Path
from typing import Any

from yoker.config import (
  MkdirToolConfig,
  ReadToolConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.tools.schema import ValidationResult


def validate_read_file_size(tool_args: dict[str, Any], config: Any) -> ValidationResult:
  """Check that a file does not exceed the maximum read size.

  Expects ``path`` in tool_args and ``max_file_size_kb`` in config.
  Skips plugin:// URLs (they are package resources, not filesystem files).
  """
  if not isinstance(config, ReadToolConfig):
    return ValidationResult(valid=True)

  max_size_kb = config.max_file_size_kb
  if max_size_kb <= 0:
    return ValidationResult(valid=True)

  path = tool_args.get("path", "")
  if not isinstance(path, str) or not path or path.startswith("plugin://"):
    return ValidationResult(valid=True)

  try:
    resolved = Path(os.path.realpath(path))
    if not resolved.exists() or not resolved.is_file():
      return ValidationResult(valid=True)

    size_bytes = resolved.stat().st_size
  except OSError:
    return ValidationResult(valid=True)

  size_kb = size_bytes / 1024
  if size_kb > max_size_kb:
    return ValidationResult(
      valid=False, reason=f"File exceeds size limit: {size_kb:.1f}KB > {max_size_kb}KB"
    )
  return ValidationResult(valid=True)


def validate_write_content_size(tool_args: dict[str, Any], config: Any) -> ValidationResult:
  """Check that write content does not exceed the maximum size.

  Expects ``content`` in tool_args and ``max_size_kb`` in config.
  """
  if not isinstance(config, WriteToolConfig):
    return ValidationResult(valid=True)

  max_size_kb = config.max_size_kb
  if max_size_kb <= 0:
    return ValidationResult(valid=True)

  content = tool_args.get("content", "")
  if not isinstance(content, str):
    return ValidationResult(valid=True)

  size_kb = len(content.encode("utf-8")) / 1024
  if size_kb > max_size_kb:
    return ValidationResult(
      valid=False, reason=f"Content exceeds size limit: {size_kb:.1f}KB > {max_size_kb}KB"
    )
  return ValidationResult(valid=True)


def validate_update_diff_size(tool_args: dict[str, Any], config: Any) -> ValidationResult:
  """Check that update diff size does not exceed the maximum.

  Expects ``new_string`` in tool_args and ``max_diff_size_kb`` in config.
  """
  if not isinstance(config, UpdateToolConfig):
    return ValidationResult(valid=True)

  max_size_kb = config.max_diff_size_kb
  if max_size_kb <= 0:
    return ValidationResult(valid=True)

  new_string = tool_args.get("new_string", "")
  if not isinstance(new_string, str):
    return ValidationResult(valid=True)

  size_kb = len(new_string.encode("utf-8")) / 1024
  if size_kb > max_size_kb:
    return ValidationResult(
      valid=False, reason=f"Diff size exceeds limit: {size_kb:.1f}KB > {max_size_kb}KB"
    )
  return ValidationResult(valid=True)


def validate_mkdir_depth(tool_args: dict[str, Any], config: Any) -> ValidationResult:
  """Check that mkdir path depth does not exceed the maximum.

  Expects ``path`` in tool_args and ``max_depth`` in config.
  """
  if not isinstance(config, MkdirToolConfig):
    return ValidationResult(valid=True)

  max_depth = config.max_depth
  if max_depth <= 0:
    return ValidationResult(valid=True)

  path = tool_args.get("path", "")
  if not isinstance(path, str) or not path:
    return ValidationResult(valid=True)

  try:
    resolved = Path(os.path.realpath(path))
  except (OSError, ValueError):
    return ValidationResult(valid=True)

  # Count path components from cwd — this is an approximate depth check
  # relative to the current working directory.
  parts = resolved.parts
  # Strip the root (e.g. "/" on Unix, "C:\\" on Windows)
  if len(parts) > 1:
    depth = len(parts) - 1
  else:
    depth = 0

  if depth >= max_depth:
    return ValidationResult(valid=False, reason=f"Path depth exceeds limit: {depth} >= {max_depth}")
  return ValidationResult(valid=True)
