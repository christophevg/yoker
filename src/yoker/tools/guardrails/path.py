"""Path guardrail implementation for Yoker filesystem tools.

Provides PathGuardrail, a concrete Guardrail that validates filesystem tool
parameters against configured permission boundaries. Prevents path traversal,
blocks sensitive patterns, enforces file size limits, filters by extension,
and protects configured files (Makefile, pyproject.toml, ...) against agent
writes via fnmatch glob matching.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from structlog import get_logger

from yoker.config import (
  Config,
  MkdirToolConfig,
  PermissionsConfig,
  ReadToolConfig,
  ToolConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.tools.guardrails import Guardrail
from yoker.tools.schema import ValidationResult

logger = get_logger(__name__)


class PathGuardrail(Guardrail):
  """Concrete guardrail for filesystem tool validation.

  Validates tool parameters against permission boundaries defined in Config:
  - Allowed filesystem paths (root containment)
  - Blocked regex patterns (e.g., .env, credentials)
  - Allowed file extensions (for read tool)
  - Maximum file size (for read tool)
  - Protected files (Makefile, pyproject.toml, ...) against agent writes

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
          logger.warning("invalid_blocked_pattern", pattern=pattern)

    # Pre-resolve allowed paths to absolute paths
    self._allowed_roots: tuple[Path, ...] = tuple(
      Path(root).resolve() for root in self._permissions.filesystem_paths
    )

  def validate(
    self, tool_name: str, value: str | dict[str, Any], *, skip_protected: bool = False
  ) -> ValidationResult:
    """Validate tool parameters against permission boundaries.

    The guardrail is only invoked for parameters annotated with ``Path``
    (via ``ToolSpec.guards``), so every call is already a filesystem path
    — no tool-name allowlist is needed.

    Steps:
      1. Extract the path parameter (from string or dict).
      2. Resolve to an absolute real path.
      3. Check the path is within allowed roots.
      4. Check blocked patterns.
      5. Tool-specific checks (read: extension/size, write: protected/
         extension/content-size, update: protected/extension/diff-size,
         file: protected, mkdir: depth).

    The ``tool_name`` is the **simple** name (e.g. ``"write"``), not the
    namespaced name (e.g. ``"yoker:write"``). The caller
    (``_validate_tool_args``) is responsible for stripping the namespace.

    Args:
      tool_name: Simple name of the tool being validated.
      value: Either a path string or a dict of tool parameters.
        When called from _validate_tool_args, this is the extracted path string.
        When called directly in tests, this may be the full params dict.

    Returns:
      ValidationResult indicating whether parameters are valid.
    """
    # Extract path from value (handle both dict and string)
    if isinstance(value, dict):
      path_param = value.get("path", "")
    else:
      path_param = value

    # Git tool allows missing path (defaults to ".")
    if not path_param:
      if tool_name == "git":
        return ValidationResult(valid=True)
      return ValidationResult(valid=False, reason="Missing required parameter: path")

    # Handle whitespace-only string paths
    if isinstance(path_param, str) and not path_param.strip():
      return ValidationResult(valid=False, reason="Path cannot be empty")

    if not isinstance(path_param, str):
      return ValidationResult(
        valid=False, reason=f"Parameter 'path' must be a string, got {type(path_param).__name__}"
      )

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
      if not skip_protected:
        protected_reason = self._check_protected_files(resolved)
        if protected_reason:
          return ValidationResult(valid=False, reason=protected_reason)

      if not skip_protected:
        ext_reason = self._check_write_extension(resolved)
        if ext_reason:
          return ValidationResult(valid=False, reason=ext_reason)

      if isinstance(value, dict):
        size_reason = self._check_write_content_size(value)
        if size_reason:
          return ValidationResult(valid=False, reason=size_reason)

    # Update-specific checks
    if tool_name == "update":
      if not resolved.exists():
        return ValidationResult(valid=False, reason=f"File not found: {path_param}")
      if not resolved.is_file():
        return ValidationResult(valid=False, reason=f"Path is not a file: {path_param}")

      if not skip_protected:
        protected_reason = self._check_protected_files(resolved)
        if protected_reason:
          return ValidationResult(valid=False, reason=protected_reason)

      if not skip_protected:
        ext_reason = self._check_write_extension(resolved)
        if ext_reason:
          return ValidationResult(valid=False, reason=ext_reason)

      if isinstance(value, dict):
        size_reason = self._check_update_diff_size(value)
        if size_reason:
          return ValidationResult(valid=False, reason=size_reason)

    # File tool checks: protected files guardrail on all paths.
    if tool_name == "file":
      if not skip_protected:
        protected_reason = self._check_protected_files(resolved)
        if protected_reason:
          return ValidationResult(valid=False, reason=protected_reason)

    # Log allowed decision
    if self._config.logging.include_permission_checks:
      logger.info("guardrail_allowed", tool=tool_name, path=str(resolved))

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

  def _relative_for_protected(self, resolved: Path) -> str:
    """Return the relative path from the containing allowed root.

    Falls back to the basename when the path is not under any allowed root
    (defensive — ``_is_within_allowed_paths`` already filters this upstream).
    POSIX-style separators are used so glob patterns like ``.git/hooks/*``
    match consistently across platforms.
    """
    for root in self._allowed_roots:
      try:
        return resolved.relative_to(root).as_posix()
      except ValueError:
        continue
    return resolved.name

  def _check_protected_files(self, resolved: Path) -> str | None:
    """Check if a resolved path matches a protected_files glob pattern.

    Matching strategy (per the owner's accepted T12 design):
      - ``fnmatch.fnmatchcase`` against each entry in ``protected_files``.
      - Matched against the relative path from the project root (the allowed
        root) AND the basename (so ``Makefile`` matches at any depth, not
        just root).

    A ``protected_files = ()`` (empty tuple) disables all protections
    (explicit opt-out).

    Args:
      resolved: The resolved absolute path to check.

    Returns:
      Error message if protected, None if allowed.
    """
    patterns = self._permissions.protected_files
    if not patterns:
      return None

    relative = self._relative_for_protected(resolved)
    basename = resolved.name
    for pattern in patterns:
      if fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(basename, pattern):
        return f"File is protected against agent writes: {relative}"
    return None

  def is_protected(self, path_str: str) -> bool:
    """Return True if ``path_str`` resolves to a protected file.

    Public entry point for the processing loop's interactive approval hook
    (which needs to know whether to invoke the approval handler without
    going through ``validate``). Performs the same fnmatch matching as
    :meth:`_check_protected_files` but returns a bool.

    Args:
      path_str: Raw path string from tool parameters.

    Returns:
      True if the path matches a ``protected_files`` entry, False otherwise.
    """
    resolved = self._resolve_path(path_str)
    if resolved is None:
      return False
    return self._check_protected_files(resolved) is not None

  def _check_read_extension(self, resolved: Path) -> str | None:
    """Check if a file extension or name is allowed for reading.

    The ``allowed_extensions`` list supports two kinds of entries:

    - **Extension entries** starting with ``.`` (e.g. ``".py"``, ``".md"``):
      matched against the file's suffix.
    - **Filename entries** without a leading dot (e.g. ``"Makefile"``,
      ``"Dockerfile"``, ``"LICENSE"``): matched against the file's name.

    This allows users to include extensionless files in the allowlist
    alongside traditional extension entries. An empty list (default)
    means all files are allowed — the ``blocked_patterns`` denylist is
    the sole filter.

    Args:
      resolved: The resolved file path.

    Returns:
      Error message if extension/name not allowed, None if allowed.
    """
    read_config = self._get_tool_config("read")
    if not isinstance(read_config, ReadToolConfig):
      return None

    allowed = read_config.allowed_extensions
    if not allowed:
      return None

    name = resolved.name
    ext = resolved.suffix.lower()

    for entry in allowed:
      if entry.startswith("."):
        if ext == entry.lower():
          return None
      else:
        if name.lower() == entry.lower():
          return None

    return f"Extension not allowed: {ext or '(none)'} (allowed: {', '.join(allowed)})"

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
      params: Tool parameters dictionary containing 'content' key.

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
      tool_name: Simple name of the tool (e.g. ``"write"``, ``"file"``).

    Returns:
      ToolConfig subclass instance, or None if not found.
    """
    try:
      return self._config.tools[tool_name]
    except (AttributeError, KeyError):
      return None

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
