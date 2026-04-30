"""Path guardrail implementation for Yoker filesystem tools.

Provides PathGuardrail, a concrete Guardrail that validates filesystem tool
parameters against configured permission boundaries. Prevents path traversal,
blocks sensitive patterns, enforces file size limits, and filters by extension.
"""

import os
import re
from pathlib import Path
from typing import Any

from yoker.config.schema import (
  Config,
  MkdirToolConfig,
  PermissionsConfig,
  ReadToolConfig,
  ToolConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.logging import get_logger
from yoker.tools.base import ValidationResult
from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)

# Tools that operate on filesystem paths
_FILESYSTEM_TOOLS = frozenset({"read", "list", "write", "update", "search", "existence", "mkdir"})


class PathGuardrail(Guardrail):
  """Concrete guardrail for filesystem tool validation.

  Validates tool parameters against permission boundaries defined in Config:
  - Allowed filesystem paths (root containment)
  - Blocked regex patterns (e.g., .env, credentials)
  - Allowed file extensions (for read tool)
  - Maximum file size (for read tool)

  Uses os.path.realpath() to resolve symlinks and normalize paths before
  validation, preventing path traversal attacks.

  Example:
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": "/etc/passwd"})
    # result.valid is False because /etc/passwd is outside allowed paths
  """

  def __init__(self, config: Config) -> None:
    """Initialize the guardrail with configuration.

    Args:
      config: Yoker configuration containing permissions and tool settings.
    """
    self._config = config
    self._permissions: PermissionsConfig = config.permissions

    # Pre-compile blocked patterns for efficiency
    self._blocked_patterns: list[re.Pattern[str]] = []
    read_config = self._get_tool_config("read")
    if isinstance(read_config, ReadToolConfig):
      for pattern in read_config.blocked_patterns:
        try:
          self._blocked_patterns.append(re.compile(pattern))
        except re.error:
          log.warning("invalid_blocked_pattern", pattern=pattern)

    # Pre-resolve allowed paths to absolute paths
    self._allowed_roots: tuple[Path, ...] = tuple(
      Path(root).resolve() for root in self._permissions.filesystem_paths
    )

  def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
    """Validate tool parameters against permission boundaries.

    Steps:
      1. Skip non-filesystem tools immediately.
      2. Extract and validate the path parameter.
      3. Resolve the path to an absolute real path.
      4. Check the path is within allowed roots.
      5. Check blocked patterns.
      6. For read tool: check extension and file size.

    Args:
      tool_name: Name of the tool being validated.
      params: Dictionary of tool parameters from the LLM.

    Returns:
      ValidationResult indicating whether parameters are valid.
    """
    # Only validate filesystem tools
    if tool_name not in _FILESYSTEM_TOOLS:
      return ValidationResult(valid=True)

    # Extract path parameter
    path_param = params.get("path")
    if path_param is None:
      return ValidationResult(valid=False, reason="Missing required parameter: path")
    if not isinstance(path_param, str):
      return ValidationResult(
        valid=False, reason=f"Parameter 'path' must be a string, got {type(path_param).__name__}"
      )
    if not path_param.strip():
      return ValidationResult(valid=False, reason="Parameter 'path' cannot be empty")

    # Resolve the path
    resolved = self._resolve_path(path_param)
    if resolved is None:
      return ValidationResult(valid=False, reason=f"Invalid or inaccessible path: {path_param}")

    # Check allowed roots first (security boundary)
    root_check = self._is_within_allowed_paths(resolved)
    if not root_check:
      return ValidationResult(valid=False, reason=f"Path outside allowed directories: {path_param}")

    # Check blocked patterns
    blocked_reason = self._check_blocked_patterns(resolved)
    if blocked_reason:
      return ValidationResult(valid=False, reason=blocked_reason)

    # Mkdir-specific checks
    if tool_name == "mkdir":
      depth_reason = self._check_mkdir_depth(resolved)
      if depth_reason:
        return ValidationResult(valid=False, reason=depth_reason)

    # Read-specific checks
    if tool_name == "read":
      # File must exist
      if not resolved.exists():
        return ValidationResult(valid=False, reason=f"File not found: {path_param}")

      ext_reason = self._check_read_extension(resolved)
      if ext_reason:
        return ValidationResult(valid=False, reason=ext_reason)

      size_reason = self._check_file_size(resolved)
      if size_reason:
        return ValidationResult(valid=False, reason=size_reason)

    # Write-specific checks
    if tool_name == "write":
      ext_reason = self._check_write_extension(resolved)
      if ext_reason:
        return ValidationResult(valid=False, reason=ext_reason)

      size_reason = self._check_write_content_size(params)
      if size_reason:
        return ValidationResult(valid=False, reason=size_reason)

    # Update-specific checks
    if tool_name == "update":
      # File must exist
      if not resolved.exists():
        return ValidationResult(valid=False, reason=f"File not found: {path_param}")
      if not resolved.is_file():
        return ValidationResult(valid=False, reason=f"Path is not a file: {path_param}")

      # Apply read extension checks (can only update allowed file types)
      ext_reason = self._check_read_extension(resolved)
      if ext_reason:
        return ValidationResult(valid=False, reason=ext_reason)

      # Apply write blocked extension checks
      ext_reason = self._check_write_extension(resolved)
      if ext_reason:
        return ValidationResult(valid=False, reason=ext_reason)

      # Check diff size
      size_reason = self._check_update_diff_size(params)
      if size_reason:
        return ValidationResult(valid=False, reason=size_reason)

    # Log allowed decision
    if self._config.logging.include_permission_checks:
      log.info("guardrail_allowed", tool=tool_name, path=str(resolved))

    return ValidationResult(valid=True)

  def _resolve_path(self, path_str: str) -> Path | None:
    """Resolve a path string to an absolute real path.

    Uses os.path.realpath() to collapse .. components and resolve symlinks.
    Returns None if the path cannot be resolved.

    Args:
      path_str: The raw path string from tool parameters.

    Returns:
      Absolute resolved Path, or None on resolution failure.
    """
    try:
      real = os.path.realpath(path_str)
      return Path(real)
    except (OSError, ValueError):
      return None

  def _is_within_allowed_paths(self, resolved: Path) -> bool:
    """Check if a resolved path is within allowed filesystem roots.

    Args:
      resolved: The resolved absolute path to check.

    Returns:
      True if the path is equal to or under an allowed root.
    """
    for root in self._allowed_roots:
      try:
        resolved.relative_to(root)
        return True
      except ValueError:
        continue
    return False

  def _check_blocked_patterns(self, resolved: Path) -> str | None:
    """Check if a path matches any blocked pattern.

    Args:
      resolved: The resolved absolute path to check.

    Returns:
      Error message if blocked, None if allowed.
    """
    path_str = str(resolved)
    for pattern in self._blocked_patterns:
      if pattern.search(path_str):
        return f"Path matches blocked pattern: {pattern.pattern}"
    return None

  def _check_read_extension(self, resolved: Path) -> str | None:
    """Check if a file extension is allowed for reading.

    Args:
      resolved: The resolved file path.

    Returns:
      Error message if extension not allowed, None if allowed.
    """
    read_config = self._get_tool_config("read")
    if not isinstance(read_config, ReadToolConfig):
      return None

    allowed = read_config.allowed_extensions
    if not allowed:
      return None

    ext = resolved.suffix.lower()
    if ext not in allowed:
      return f"Extension not allowed: {ext} (allowed: {', '.join(allowed)})"
    return None

  def _check_file_size(self, resolved: Path) -> str | None:
    """Check if a file exceeds the maximum allowed size.

    Args:
      resolved: The resolved file path.

    Returns:
      Error message if file too large, None if within limits.
    """
    max_size_kb = self._permissions.max_file_size_kb
    if max_size_kb <= 0:
      return None

    try:
      size_bytes = resolved.stat().st_size
    except OSError:
      return None

    size_kb = size_bytes / 1024
    if size_kb > max_size_kb:
      return f"File exceeds size limit: {size_kb:.1f}KB > {max_size_kb}KB"
    return None

  def _check_write_extension(self, resolved: Path) -> str | None:
    """Check if a file extension is blocked for writing.

    Args:
      resolved: The resolved file path.

    Returns:
      Error message if extension is blocked, None if allowed.
    """
    write_config = self._get_tool_config("write")
    if not isinstance(write_config, WriteToolConfig):
      return None

    blocked = write_config.blocked_extensions
    if not blocked:
      return None

    ext = resolved.suffix.lower()
    if ext in blocked:
      return f"Extension blocked for writing: {ext}"
    return None

  def _check_write_content_size(self, params: dict[str, Any]) -> str | None:
    """Check if write content exceeds the maximum allowed size.

    Args:
      params: Tool parameters dictionary.

    Returns:
      Error message if content too large, None if within limits.
    """
    write_config = self._get_tool_config("write")
    if not isinstance(write_config, WriteToolConfig):
      return None

    max_size_kb = write_config.max_size_kb
    if max_size_kb <= 0:
      return None

    content = params.get("content", "")
    if not isinstance(content, str):
      return None

    size_kb = len(content.encode("utf-8")) / 1024
    if size_kb > max_size_kb:
      return f"Content exceeds size limit: {size_kb:.1f}KB > {max_size_kb}KB"
    return None

  def _check_update_diff_size(self, params: dict[str, Any]) -> str | None:
    """Check if update diff size exceeds the maximum allowed.

    Args:
      params: Tool parameters dictionary with old_string and new_string.

    Returns:
      Error message if diff too large, None if within limits.
    """
    update_config = self._get_tool_config("update")
    if not isinstance(update_config, UpdateToolConfig):
      return None

    max_size_kb = update_config.max_diff_size_kb
    if max_size_kb <= 0:
      return None

    new_string = params.get("new_string", "")
    if not isinstance(new_string, str):
      return None

    size_kb = len(new_string.encode("utf-8")) / 1024
    if size_kb > max_size_kb:
      return f"Diff size exceeds limit: {size_kb:.1f}KB > {max_size_kb}KB"
    return None

  def _get_tool_config(self, tool_name: str) -> ToolConfig | None:
    """Get tool-specific configuration by name.

    Args:
      tool_name: Name of the tool.

    Returns:
      ToolConfig subclass instance, or None if not found.
    """
    tools = self._config.tools
    mapping: dict[str, ToolConfig] = {
      "list": tools.list,
      "read": tools.read,
      "write": tools.write,
      "update": tools.update,
      "search": tools.search,
      "agent": tools.agent,
      "git": tools.git,
      "mkdir": tools.mkdir,
    }
    return mapping.get(tool_name)

  def _check_mkdir_depth(self, resolved: Path) -> str | None:
    """Check if path depth exceeds maximum allowed from allowed root.

    Args:
      resolved: The resolved absolute path to check.

    Returns:
      Error message if depth exceeds limit, None if within limits.
    """
    mkdir_config = self._get_tool_config("mkdir")
    if not isinstance(mkdir_config, MkdirToolConfig):
      return None

    max_depth = mkdir_config.max_depth
    if max_depth <= 0:
      return None

    # Find the allowed root that contains this path
    for root in self._allowed_roots:
      try:
        relative = resolved.relative_to(root)
        # Count path components (depth from root)
        depth = len(relative.parts)
        if depth >= max_depth:
          return f"Path depth exceeds limit: {depth} >= {max_depth}"
        return None
      except ValueError:
        continue

    # Path is not under any allowed root (shouldn't happen if _is_within_allowed_paths passed)
    return None
