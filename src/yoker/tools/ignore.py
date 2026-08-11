"""Gitignore-style pattern matching for file traversal tools.

Provides a pragmatic parser for ``.gitignore``-style files that covers the
most common patterns:

- Bare names (``context/``, ``logs``)
- Wildcards (``*.jsonl``, ``*.py[cod]``)
- Anchored paths (``/yoker.toml``)
- Trailing slash for directory-only matches (``build/``)
- Negation (``!important.log``)
- ``**`` double-star for cross-directory matching

Patterns are relative to the directory in which the ignore file lives,
matching git semantics for nested ``.gitignore`` files.

This is NOT a 100% git-compatible implementation — it covers the 90%+
case. Edge cases in git's gitignore handling (e.g. complex ``**``
interactions, ordered negation across nested files) may differ slightly.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class IgnorePattern:
  """A single parsed gitignore-style pattern.

  Attributes:
    raw: The original pattern text (without trailing newline).
    negation: Whether this is a negation pattern (starts with ``!``).
    dir_only: Whether this matches directories only (trailing ``/``).
    anchored: Whether this is anchored to the ignore file's directory
      (leading ``/`` or contains a ``/`` in the middle).
    regex: Compiled regex matcher for this pattern, or None if it's a
      simple glob handled via fnmatch.
    glob: The glob string for fnmatch-based matching, or None.
  """

  raw: str
  negation: bool = False
  dir_only: bool = False
  anchored: bool = False
  regex: re.Pattern[str] | None = None
  glob: str | None = None


@dataclass
class IgnoreFile:
  """Parsed ignore file with its root directory.

  Attributes:
    root_dir: The directory this ignore file applies to (patterns are
      relative to this directory).
    patterns: Ordered list of parsed patterns (negation patterns come
      after the patterns they negate, matching git semantics).
  """

  root_dir: Path
  patterns: list[IgnorePattern] = field(default_factory=list)


def parse_ignore_file(path: Path) -> IgnoreFile | None:
  """Parse a single ignore file.

  Args:
    path: Path to the ignore file (e.g. ``.gitignore``).

  Returns:
    ``IgnoreFile`` with parsed patterns, or ``None`` if the file doesn't
    exist or is empty.
  """
  if not path.is_file():
    return None

  try:
    content = path.read_text(encoding="utf-8", errors="replace")
  except OSError:
    return None

  root_dir = path.parent
  patterns: list[IgnorePattern] = []

  for line in content.splitlines():
    # Strip trailing whitespace but not leading (git behavior)
    stripped = line.rstrip()
    if not stripped:
      continue
    # Comments
    if stripped.startswith("#"):
      continue

    pattern = _parse_line(stripped)
    if pattern is not None:
      patterns.append(pattern)

  if not patterns:
    return None

  return IgnoreFile(root_dir=root_dir, patterns=patterns)


def _parse_line(line: str) -> IgnorePattern | None:
  """Parse a single gitignore line into an IgnorePattern."""
  raw = line

  # Handle negation
  negation = False
  if line.startswith("!"):
    negation = True
    line = line[1:]

  # Handle trailing slash (directory-only)
  dir_only = False
  if line.endswith("/"):
    dir_only = True
    line = line[:-1]

  # Handle escaped characters (\# or \!)
  line = line.replace("\\#", "#").replace("\\!", "!")

  if not line:
    return None

  # Anchored: leading slash or contains a slash
  anchored = False
  if line.startswith("/"):
    anchored = True
    line = line[1:]
  elif "/" in line:
    anchored = True

  # Convert to regex if it contains **, otherwise use fnmatch
  if "**" in line:
    regex = _glob_to_regex(line, anchored)
    return IgnorePattern(
      raw=raw,
      negation=negation,
      dir_only=dir_only,
      anchored=anchored,
      regex=regex,
    )
  else:
    return IgnorePattern(
      raw=raw,
      negation=negation,
      dir_only=dir_only,
      anchored=anchored,
      glob=line,
    )


def _glob_to_regex(pattern: str, anchored: bool) -> re.Pattern[str]:
  """Convert a glob pattern with ** support to a compiled regex.

  ``**`` matches any number of directories. ``*`` matches within a path
  segment. ``?`` matches a single character.
  """
  parts: list[str] = []
  i = 0
  while i < len(pattern):
    c = pattern[i]
    if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
      # ** — match any number of path segments
      # Consume following slash if present
      if i + 2 < len(pattern) and pattern[i + 2] == "/":
        parts.append(".*")
        i += 3
      else:
        parts.append(".*")
        i += 2
    elif c == "*":
      parts.append("[^/]*")
      i += 1
    elif c == "?":
      parts.append("[^/]")
      i += 1
    elif c == "/":
      parts.append("/")
      i += 1
    else:
      parts.append(re.escape(c))
      i += 1

  regex_str = "".join(parts)

  if anchored:
    # Anchored: match from the root_dir
    full = f"^{regex_str}$"
  else:
    # Non-anchored: match at any path level
    full = f"(^|.*/){regex_str}$"

  return re.compile(full)


class IgnoreMatcher:
  """Matches file paths against a set of ignore files.

  Created once per tool invocation from the search/list root directory.
  Walks up from the root to find ignore files, then provides
  ``should_ignore()`` for each file encountered during traversal.
  """

  def __init__(
    self,
    root: Path,
    ignore_files: tuple[str, ...] = (".gitignore",),
    skip_dirs: tuple[str, ...] = (),
    skip_dotfiles: bool = True,
    respect_ignore_files: bool = True,
  ) -> None:
    self.root = root.resolve()
    self.skip_dirs = frozenset(skip_dirs)
    self.skip_dotfiles = skip_dotfiles
    self.respect_ignore_files = respect_ignore_files
    self._ignore_files: list[IgnoreFile] = []

    if respect_ignore_files and root.is_dir():
      self._ignore_files = _collect_ignore_files(root, ignore_files)

  def should_skip_dir(self, dirname: str) -> bool:
    """Check if a directory name should be pruned from traversal.

    This checks the hardcoded skip_dirs and dotfile rules. Ignore-file
    patterns are checked separately via ``should_ignore_path()``.
    """
    if dirname in self.skip_dirs:
      return True
    if self.skip_dotfiles and dirname.startswith("."):
      return True
    return False

  def should_ignore_path(self, file_path: Path, is_dir: bool = False) -> bool:
    """Check if a file/directory path should be ignored.

    Applies both the hardcoded skip rules and the parsed ignore-file
    patterns. Negation patterns can un-ignore previously ignored paths.

    Args:
      file_path: Absolute path to the file/directory.
      is_dir: Whether the path is a directory (for dir_only patterns).

    Returns:
      True if the path should be ignored (excluded from results).
    """
    name = file_path.name

    # Hardcoded skip_dirs and dotfiles
    if name in self.skip_dirs:
      return True
    if self.skip_dotfiles and name.startswith("."):
      return True

    # Ignore-file patterns
    if not self._ignore_files:
      return False

    ignored = False
    for ignore_file in self._ignore_files:
      try:
        rel = file_path.relative_to(ignore_file.root_dir)
      except ValueError:
        # file_path is not under this ignore file's root
        continue

      rel_str = rel.as_posix()

      for pattern in ignore_file.patterns:
        if _matches_pattern(pattern, rel_str, is_dir=is_dir):
          if pattern.negation:
            ignored = False
          else:
            ignored = True

    return ignored


def _matches_pattern(pattern: IgnorePattern, rel_path: str, is_dir: bool = False) -> bool:
  """Check if a relative path matches a single ignore pattern.

  For dir_only patterns:
  - If the path itself is a directory, match against the full path.
  - If the path is a file, match if any parent directory matches the pattern.
  """
  if pattern.dir_only:
    parts = rel_path.split("/")
    # Check if the path itself (if dir) or any parent directory matches
    for i in range(len(parts)):
      sub = "/".join(parts[: i + 1])
      # The last segment is only checked if this path is a directory
      if i == len(parts) - 1 and not is_dir:
        continue
      if _matches_single(pattern, sub):
        return True
    return False

  return _matches_single(pattern, rel_path)


def _matches_single(pattern: IgnorePattern, rel_path: str) -> bool:
  """Check a single path string against a single pattern."""
  if pattern.regex is not None:
    return bool(pattern.regex.match(rel_path))

  if pattern.glob is None:
    return False

  if pattern.anchored:
    # Anchored: match the full relative path
    return fnmatch.fnmatchcase(rel_path, pattern.glob)
  else:
    # Non-anchored: match the basename or any path prefix
    # "*.jsonl" should match "foo/bar.jsonl" and "bar.jsonl"
    # "context" should match "context" and "src/context"
    basename = rel_path.split("/")[-1]
    if fnmatch.fnmatchcase(basename, pattern.glob):
      return True
    # Also match full path for patterns containing wildcards
    if "*" in pattern.glob or "?" in pattern.glob or "[" in pattern.glob:
      return fnmatch.fnmatchcase(rel_path, pattern.glob)
    # For plain names, also check if any path segment matches
    # (e.g. "build" matches "src/build/foo.py")
    parts = rel_path.split("/")
    for part in parts[:-1]:  # parent directories
      if fnmatch.fnmatchcase(part, pattern.glob):
        return True
    return False


def _collect_ignore_files(
  root: Path,
  ignore_filenames: tuple[str, ...],
) -> list[IgnoreFile]:
  """Collect ignore files from root and all parent directories up to /
  or the first .git directory.

  Also collects nested ignore files within root (e.g.
  ``root/src/.gitignore``). Files are ordered root-first (outermost
  patterns first, innermost last), matching git's precedence rules
  where inner files override outer ones.
  """
  result: list[IgnoreFile] = []

  # 1. Walk up from root to find ignore files in parent directories
  #    (stop at filesystem root or .git directory)
  parents: list[Path] = []
  current = root
  while current != current.parent:
    parents.append(current)
    git_dir = current / ".git"
    if git_dir.is_dir():
      break
    current = current.parent
  parents.append(current)  # filesystem root

  # Process outermost-first
  for parent in reversed(parents):
    for name in ignore_filenames:
      ignore_file = parse_ignore_file(parent / name)
      if ignore_file is not None:
        result.append(ignore_file)

  # 2. Walk root's subtree to find nested ignore files
  #    (only within root, not in parent directories already covered)
  try:
    walk_iter = os.walk(root)
  except PermissionError:
    walk_iter = iter([])
  for dirpath, dirnames, filenames in walk_iter:
    # Prune skip dirs to avoid walking into .git, etc.
    dirnames[:] = [
      d
      for d in dirnames
      if d not in (".git", "__pycache__", ".venv", "venv", "node_modules") and not d.startswith(".")
    ]
    for name in ignore_filenames:
      if name in filenames:
        ignore_file = parse_ignore_file(Path(dirpath) / name)
        if ignore_file is not None:
          result.append(ignore_file)

  return result


__all__ = [
  "IgnorePattern",
  "IgnoreFile",
  "IgnoreMatcher",
  "parse_ignore_file",
]
