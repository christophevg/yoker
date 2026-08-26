"""Path guardrail implementation for Yoker filesystem tools.

Provides ``ReadPathGuardrail`` and ``WritePathGuardrail``, concrete
Guardrails that validate filesystem tool parameters against configured
permission boundaries.

The access control pipeline is three layers, checked in order:

1. ``filesystem_paths`` (HARD) — spatial boundary: which roots are accessible
2. ``blocked_paths`` (HARD) — universal denylist: what's blocked within roots
3. ``blocked_write_paths`` (SOFT) — write-only denylist: additional blocks
   for write operations (WritePathGuardrail only)

``ReadPathGuardrail`` implements layers 1–2.
``WritePathGuardrail`` subclasses it and adds layer 3.

Glob patterns are matched case-insensitively against the relative path
from the containing allowed root. Full glob support: ``*`` (one segment),
``**`` (zero or more segments), ``?``, ``[...]``.

Paths are resolved with ``os.path.realpath()`` before any checks, collapsing
symlinks and ``..`` components. This prevents path traversal and symlink
escape.

The special ``"plugin://"`` entry in ``filesystem_paths`` allows read tools
to access ``plugin://`` URLs (package resources, not filesystem paths).
"""

import os
import re
from pathlib import Path
from typing import Any

from structlog import get_logger

from yoker.config import Config, PermissionsConfig
from yoker.tools.guardrails import Guardrail
from yoker.tools.schema import ValidationResult

logger = get_logger(__name__)

# Prefix for plugin resource URLs — not a filesystem path.
_PLUGIN_PREFIX = "plugin://"


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
  """Translate a glob pattern to a compiled case-insensitive regex.

  Supports:
    - ``**`` — zero or more path segments (including slashes)
    - ``*`` — one path segment (no slashes)
    - ``?`` — any single character (no slashes)
    - ``[...]`` — character class

  Args:
    pattern: Glob pattern string.

  Returns:
    Compiled case-insensitive regex pattern.
  """
  result: list[str] = ["(?i)"]
  i = 0
  while i < len(pattern):
    c = pattern[i]
    if c == "*":
      if i + 1 < len(pattern) and pattern[i + 1] == "*":
        # ** — matches anything including /
        result.append(".*")
        i += 2
      else:
        # * — matches one segment (no /)
        result.append("[^/]*")
        i += 1
    elif c == "?":
      result.append("[^/]")
      i += 1
    elif c == "[":
      # Character class — find closing ]
      j = i + 1
      if j < len(pattern) and pattern[j] == "!":
        j += 1
      if j < len(pattern) and pattern[j] == "]":
        j += 1
      while j < len(pattern) and pattern[j] != "]":
        j += 1
      if j < len(pattern):
        result.append(pattern[i : j + 1])
        i = j + 1
      else:
        # No closing ] — treat [ as literal
        result.append(re.escape(c))
        i += 1
    elif c == "/":
      result.append("/")
      i += 1
    else:
      result.append(re.escape(c))
      i += 1
  return re.compile("".join(result) + "$")


def compile_blocked_patterns(patterns: tuple[str, ...]) -> list[re.Pattern[str]]:
  """Compile a tuple of glob patterns into regex patterns for matching.

  Used by tools that need to check ``blocked_paths`` internally during
  traversal (e.g. ``search``, ``list``). The compiled patterns are passed
  to :func:`is_path_blocked`.

  Args:
    patterns: Glob pattern strings from ``blocked_paths`` config.

  Returns:
    List of compiled case-insensitive regex patterns.
  """
  return [_glob_to_regex(p) for p in patterns]


def is_path_blocked(
  file_path: Path,
  root: Path,
  blocked_patterns: list[re.Pattern[str]],
) -> bool:
  """Check if a file's relative path matches any blocked_path pattern.

  Used by traversal tools (``search``, ``list``) to enforce the universal
  ``blocked_paths`` denylist on every file they touch — preventing bypass
  via ``search`` reading content of files that would be blocked by the
  guardrail.

  Patterns are matched against the relative path from root AND the
  absolute path. Matching a directory blocks it and everything beneath it
  — so ``local`` blocks both ``local`` and ``local/hard.md``. This is
  achieved by checking the full path AND every ancestor (prefix) against
  each pattern.

  Args:
    file_path: Absolute path to the file/directory.
    root: The traversal root (an allowed root).
    blocked_patterns: Compiled glob regex patterns from ``compile_blocked_patterns``.

  Returns:
    True if the file should be skipped, False otherwise.
  """
  if not blocked_patterns:
    return False

  candidates: list[str] = []
  try:
    relative = file_path.relative_to(root).as_posix()
    candidates.append(relative)
  except ValueError:
    pass  # Outside root — will be caught by absolute path check below
  candidates.append(str(file_path))

  for candidate in candidates:
    parts = candidate.split("/")
    for i in range(len(parts), 0, -1):
      ancestor = "/".join(parts[:i])
      for pattern in blocked_patterns:
        if pattern.match(ancestor):
          return True
  return False


class ReadPathGuardrail(Guardrail):
  """Guardrail for read-only filesystem path validation.

  Implements layers 1–2 of the access control pipeline:
    1. Path must be within ``filesystem_paths`` (HARD)
    2. Path must not match ``blocked_paths`` (HARD)

  The ``"plugin://"`` special entry in ``filesystem_paths`` allows
  ``plugin://`` URLs to pass through (they are package resources, not
  filesystem paths).
  """

  def __init__(self, config: Config) -> None:
    self._config = config
    self._permissions: PermissionsConfig = config.permissions

    # Pre-compile blocked_paths glob patterns
    self._blocked_path_patterns: list[re.Pattern[str]] = [
      _glob_to_regex(p) for p in self._permissions.blocked_paths
    ]
    # Pre-resolve patterns that look like relative paths (contain / or ..)
    # These are resolved relative to each allowed root, not cwd
    self._blocked_path_resolved: list[Path] = []
    fs_entries = [r for r in self._permissions.filesystem_paths if not r.startswith(_PLUGIN_PREFIX)]
    allowed_roots_for_resolution = [Path(root).expanduser() for root in fs_entries]
    for p in self._permissions.blocked_paths:
      if "/" in p or p.startswith("..") or p.startswith("~"):
        # Resolve relative to each allowed root
        for root in allowed_roots_for_resolution:
          try:
            resolved_pattern = (root / p).expanduser().resolve()
            self._blocked_path_resolved.append(resolved_pattern)
          except (OSError, ValueError):
            pass
        # Also try resolving from cwd for absolute or ~ patterns
        if not p.startswith(".."):
          try:
            resolved_pattern = Path(p).expanduser().resolve()
            self._blocked_path_resolved.append(resolved_pattern)
          except (OSError, ValueError):
            pass

    # Separate filesystem roots from special entries (plugin://)
    self._allowed_roots: tuple[Path, ...] = tuple(
      Path(root).expanduser().resolve() for root in fs_entries
    )
    self._allows_plugin: bool = any(
      r.startswith(_PLUGIN_PREFIX) for r in self._permissions.filesystem_paths
    )

  def validate(
    self, tool_name: str, value: str | dict[str, Any], *, skip_blocks: bool = False
  ) -> ValidationResult:
    """Validate a read-only filesystem path parameter.

    Args:
      tool_name: Simple tool name (unused — guardrail is tool-agnostic).
      value: Path string or dict containing a "path" key.
      skip_blocks: Ignored for read guardrail (no soft blocks).

    Returns:
      ValidationResult indicating whether the path is allowed.
    """
    path_param = self._extract_path(value)
    if path_param is None:
      return ValidationResult(valid=False, reason="Missing required parameter: path")

    if not path_param.strip():
      return ValidationResult(valid=False, reason="Path cannot be empty")

    # plugin:// URLs — allowed if configured
    if path_param.startswith(_PLUGIN_PREFIX):
      if self._allows_plugin:
        return ValidationResult(valid=True)
      return ValidationResult(valid=False, reason=f"Plugin URLs not allowed: {path_param}")

    resolved = self._resolve_path(path_param)
    if resolved is None:
      return ValidationResult(valid=False, reason=f"Invalid or inaccessible path: {path_param}")

    # Layer 1: filesystem_paths (HARD)
    if not self._is_within_allowed_paths(resolved):
      return ValidationResult(valid=False, reason=f"Path outside allowed directories: {path_param}")

    # Layer 2: blocked_paths (HARD)
    blocked_reason = self._check_blocked_paths(resolved)
    if blocked_reason:
      return ValidationResult(valid=False, reason=blocked_reason)

    if self._config.logging.include_permission_checks:
      logger.info("guardrail_allowed", tool=tool_name, path=str(resolved))

    return ValidationResult(valid=True)

  def _extract_path(self, value: str | dict[str, Any]) -> str | None:
    """Extract the path string from a string or dict value."""
    if isinstance(value, dict):
      path_param = value.get("path", "")
      if not path_param:
        # Try "source" (file tool) or "cwd" (make tool)
        path_param = value.get("source", value.get("cwd", ""))
      # For file tool, also check "destination" (for copy/move operations)
      if not path_param:
        path_param = value.get("destination", "")
      return path_param if isinstance(path_param, str) else None
    if isinstance(value, str):
      return value
    return None

  def _resolve_path(self, path_str: str) -> Path | None:
    """Resolve a path string to an absolute real path.

    Uses ``os.path.realpath()`` to collapse ``..`` components and resolve
    symlinks. Returns None if the path cannot be resolved.
    """
    try:
      real = os.path.realpath(path_str)
      return Path(real)
    except (OSError, ValueError):
      return None

  def _is_within_allowed_paths(self, resolved: Path) -> bool:
    """Check if a resolved path is within allowed filesystem roots."""
    for root in self._allowed_roots:
      try:
        resolved.relative_to(root)
        return True
      except ValueError:
        continue
    return False

  def _relative_to_root(self, resolved: Path) -> str:
    """Return the relative path (POSIX-style) from the containing allowed root.

    Falls back to the basename when the path is not under any allowed root.
    """
    for root in self._allowed_roots:
      try:
        return resolved.relative_to(root).as_posix()
      except ValueError:
        continue
    return resolved.name

  def _check_blocked_paths(self, resolved: Path) -> str | None:
    """Check if a path matches any blocked_paths glob pattern.

    Patterns are matched against the relative path from the containing
    allowed root AND the absolute path. This supports both root-relative
    patterns (e.g. ``local``, ``.git``) and absolute/parent-relative
    patterns (e.g. ``../yoker-test``, ``/etc/secrets``).

    Case-insensitive. Matching a directory blocks it and everything beneath
    — so ``local`` blocks both ``local`` and ``local/hard.md``. This is
    achieved by checking the full path AND every ancestor (prefix) against
    each pattern.
    """
    result = self._match_patterns_with_ancestors(
      resolved, self._blocked_path_patterns, "Path matches blocked pattern"
    )
    if result is not None:
      return result
    # Check resolved absolute patterns
    for blocked_root in self._blocked_path_resolved:
      if resolved == blocked_root or blocked_root in resolved.parents:
        return f"Path matches blocked pattern: {self._relative_to_root(resolved)}"
    return None

  def _match_patterns_with_ancestors(
    self, resolved: Path, patterns: list[re.Pattern[str]], label: str
  ) -> str | None:
    """Match patterns against multiple path representations and ancestors.

    Checks two representations of the path:
    1. Relative path from the containing allowed root (e.g. ``local/hard.md``)
    2. Absolute resolved path (e.g. ``/home/user/proj/local/hard.md``)

    For each representation, checks the full path AND every ancestor
    directory prefix, so that matching a directory blocks everything
    beneath it.

    Glob patterns follow standard semantics:
    - ``local`` matches only at root level
    - ``**/local`` matches at any depth
    - ``local/**`` matches everything under local/
    """
    candidates: list[str] = []
    relative = self._relative_to_root(resolved)
    if relative:
      candidates.append(relative)
    candidates.append(str(resolved))

    for candidate in candidates:
      parts = candidate.split("/")
      for i in range(len(parts), 0, -1):
        ancestor = "/".join(parts[:i])
        for pattern in patterns:
          if pattern.match(ancestor):
            return f"{label}: {relative}"
    return None


class WritePathGuardrail(ReadPathGuardrail):
  """Guardrail for write-mode filesystem path validation.

  Subclasses ``ReadPathGuardrail`` and adds layer 3:
    3. Path must not match ``blocked_write_paths`` (SOFT — user can approve
       interactively; HARD in batch mode).

  The ``skip_blocks`` flag (set by the interactive approval flow) skips
  the ``blocked_write_paths`` check for this call.
  """

  def __init__(self, config: Config) -> None:
    super().__init__(config)
    self._blocked_write_path_patterns: list[re.Pattern[str]] = [
      _glob_to_regex(p) for p in self._permissions.blocked_write_paths
    ]
    # Also pre-resolve patterns that look like relative paths (contain / or ..)
    # to absolute paths, so they can be matched against absolute file paths.
    # Resolve relative to each allowed root, not cwd
    self._blocked_write_path_resolved: list[Path] = []
    for p in self._permissions.blocked_write_paths:
      if "/" in p or p.startswith("..") or p.startswith("~"):
        # Resolve relative to each allowed root
        for root in self._allowed_roots:
          try:
            resolved_pattern = (root / p).expanduser().resolve()
            self._blocked_write_path_resolved.append(resolved_pattern)
          except (OSError, ValueError):
            pass
        # Also try resolving from cwd for absolute or ~ patterns (not ..)
        if not p.startswith(".."):
          try:
            resolved_pattern = Path(p).expanduser().resolve()
            self._blocked_write_path_resolved.append(resolved_pattern)
          except (OSError, ValueError):
            pass

  def validate(
    self, tool_name: str, value: str | dict[str, Any], *, skip_blocks: bool = False
  ) -> ValidationResult:
    """Validate a write-mode filesystem path parameter.

    Runs layers 1–2 from the read guardrail, then layer 3 (blocked_write_paths)
    unless ``skip_blocks`` is True.
    """
    path_param = self._extract_path(value)
    if path_param is None:
      return ValidationResult(valid=False, reason="Missing required parameter: path")

    if not path_param.strip():
      return ValidationResult(valid=False, reason="Path cannot be empty")

    # plugin:// URLs don't make sense for write operations
    if path_param.startswith(_PLUGIN_PREFIX):
      return ValidationResult(
        valid=False, reason=f"Plugin URLs not supported for write operations: {path_param}"
      )

    resolved = self._resolve_path(path_param)
    if resolved is None:
      return ValidationResult(valid=False, reason=f"Invalid or inaccessible path: {path_param}")

    # Layer 1: filesystem_paths (HARD)
    if not self._is_within_allowed_paths(resolved):
      return ValidationResult(valid=False, reason=f"Path outside allowed directories: {path_param}")

    # Layer 2: blocked_paths (HARD)
    blocked_reason = self._check_blocked_paths(resolved)
    if blocked_reason:
      return ValidationResult(valid=False, reason=blocked_reason)

    # Layer 3: blocked_write_paths (SOFT — skipped when skip_blocks=True)
    if not skip_blocks:
      write_blocked_reason = self._check_blocked_write_paths(resolved)
      if write_blocked_reason:
        return ValidationResult(valid=False, reason=write_blocked_reason)

    if self._config.logging.include_permission_checks:
      logger.info("guardrail_allowed", tool=tool_name, path=str(resolved))

    return ValidationResult(valid=True)

  def _check_blocked_write_paths(self, resolved: Path) -> str | None:
    """Check if a path matches any blocked_write_paths glob pattern.

    Uses the same ancestor-prefix and dual-path matching as
    ``_check_blocked_paths``. Additionally checks resolved absolute patterns
    (patterns containing ``/`` or starting with ``.`` are resolved to
    absolute paths and matched against the resolved file path).
    """
    result = self._match_patterns_with_ancestors(
      resolved, self._blocked_write_path_patterns, "File is write-protected"
    )
    if result is not None:
      return result
    # Check resolved absolute patterns (e.g. "../yoker-test" → "/abs/path")
    for blocked_root in self._blocked_write_path_resolved:
      if resolved == blocked_root or blocked_root in resolved.parents:
        return f"File is write-protected: {self._relative_to_root(resolved)}"
    return None

  def is_write_blocked(self, path_str: str) -> bool:
    """Return True if ``path_str`` resolves to a write-protected file.

    Public entry point for the processing loop's interactive approval hook.
    Checks only ``blocked_write_paths`` — assumes layers 1–2 already passed.
    """
    resolved = self._resolve_path(path_str)
    if resolved is None:
      return False
    return self._check_blocked_write_paths(resolved) is not None
